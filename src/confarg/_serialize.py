# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Serialization of dataclass instances to plain dicts (the inverse of construction).

Dev Notes:
    docs-dev/architecture/types/serialization.md#serialization
"""

from __future__ import annotations

import enum
import warnings
from typing import TYPE_CHECKING, Any

from confarg import _defaults
from confarg._callable import _serialize_callable, holds_an_opener, promote_bare_spec
from confarg._cast import cast_name_for_type
from confarg._import import dotted_name, imports_back
from confarg._merge import ListOp, MergeDict, _DeleteSentinel
from confarg._types import (
    TagPolicy,
    _dict_kv,
    _elem_type,
    _fixed_seq_types,
    _is_callable,
    _is_list,
    _is_literal,
    _is_struct,
    _literal_values,
    _namedtuple_fields,
    _origin,
    _Pinned,
    _resolve_type,
    _StrToken,
    _struct_fields,
    _tuple_types,
    _union_args_no_none,
)
from confarg.exceptions import ConfargError, ConfargWarning, FieldPath, _spell_field_path
from confarg.typedload._coerce import _LEAF_SERIALIZERS, _is_struct_variant, _type_kind, _TypeKind
from confarg.typedload._construct import _disambiguate_struct, _holds_anything, construct

if TYPE_CHECKING:
    from collections.abc import Callable


def _serialize(
    tp: Any,
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
) -> Any:
    """Serialize a typed value to a plain dict/list/leaf structure.

    Args:
        tp: The declared type of the value.
        instance: The value to serialize.
        path: The field's path below the instance, which diagnostics name.
        union_tag: The field name used as a discriminator tag in unions.
        tag_policy: "auto" or "always".

    Returns:
        A JSON-compatible structure (dict, list, or leaf value).
    """
    tp = _resolve_type(tp)
    if instance is None:
        return None
    return _serialize_by_type(tp, instance, path, union_tag, tag_policy)


def _serialize_by_type(  # noqa: PLR0911  # one return per kind
    tp: Any,
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
) -> Any:
    """Dispatch serialization on the shape :func:`_type_kind` names, after None is handled."""
    match _type_kind(tp):
        case _TypeKind.UNION:
            return _serialize_union(tp, instance, path, union_tag, tag_policy)
        case _TypeKind.NAMEDTUPLE:
            return _serialize_namedtuple(tp, instance, path, union_tag, tag_policy)
        case _TypeKind.STRUCT:
            return _serialize_struct(tp, instance, path, union_tag, tag_policy)
        case _TypeKind.LIST | _TypeKind.SET | _TypeKind.FROZENSET:
            return _serialize_collection(tp, instance, path, union_tag, tag_policy)
        case _TypeKind.TUPLE:
            return _serialize_tuple(tp, instance, path, union_tag, tag_policy)
        case _TypeKind.DICT:
            return _serialize_dict(tp, instance, path, union_tag, tag_policy)
        case _TypeKind.CALLABLE:
            # A partial's keywords carry no declared type: they leave as a raw dict's values do. A
            # callable instance, or a method's owner, is a struct, its fields serialized as their types say.
            spec = _serialize_callable(
                instance,
                lambda owner: _serialize_struct(type(owner), owner, path, union_tag, tag_policy),
            )
            return _serialize_untyped(spec)
        case _TypeKind.ANY:
            return _serialize_any(instance, path, union_tag, tag_policy)
        case _TypeKind.TAGGABLE_LEAF | _TypeKind.LEAF:
            return _serialize_leaf(tp, instance)


def _serialize_any(
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
    *,
    checked: bool = True,
) -> Any:
    """Serialize what an ``Any`` node holds by its runtime type, as the spec that rebuilds it.

    A dict and a list are walked, each item an ``Any`` node in turn; a tuple or a set is
    written as the list a file holds. Any other value is written by :func:`_held_object_form`.

    *checked*, each value is kept only when an ``Any`` node reads it back as the value it
    came from (:func:`_reads_back`), an object compared by the state it holds; any other is
    written untyped (:func:`_serialize_untyped`), with a :class:`ConfargWarning` saying why.
    A dict holding an opener key, which reads back as a spec, and a tuple or a set, which
    reads back as a list, warn too. Unchecked, the form is returned as it is, and a value no
    spec can write raises.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """

    def item(value: Any, key: str | int) -> Any:
        if value is None:
            return None
        return _serialize_any(value, (*path, key), union_tag, tag_policy, checked=checked)

    if isinstance(instance, dict):
        out = {_data_key(_serialize_leaf(None, k), (*path, str(k))): item(v, str(k)) for k, v in instance.items()}
        if checked and holds_an_opener(out):
            _warn_unread_any(instance, path, "it holds an opener key, so it reads back as the spec it spells")
        return out
    if isinstance(instance, list):
        return [item(v, i) for i, v in enumerate(instance)]
    if isinstance(instance, (tuple, set, frozenset)):
        items = [item(v, i) for i, v in enumerate(instance)]
        if not isinstance(instance, tuple):
            items.sort(key=_sort_key)
        if checked:
            _warn_unread_any(instance, path, "an Any node reads a sequence back as a list")
        return items
    if checked:
        return _serialize_held_object(instance, path, union_tag, tag_policy)
    return _held_object_form(instance, path, union_tag, tag_policy)


def _serialize_held_object(instance: Any, path: FieldPath, union_tag: str, tag_policy: TagPolicy) -> Any:
    """Serialize a value an ``Any`` node holds, no container, as its spec when an ``Any`` node reads it back.

    Any other is written untyped (:func:`_serialize_untyped`), with a :class:`ConfargWarning`
    saying why (:func:`_serialize_any`).

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """
    # What the fields of a struct warn belongs to the spec, so it is said only if the spec is kept.
    unwritable: ConfargError | None = None
    with warnings.catch_warnings(record=True) as within:
        warnings.simplefilter("always", ConfargWarning)
        try:
            written = _held_object_form(instance, path, union_tag, tag_policy)
        except ConfargError as e:
            unwritable = e
    if unwritable is not None:
        _warn_unread_any(instance, path, str(unwritable))
        return _serialize_untyped(instance)

    def dumps_as(back: Any) -> Any:
        return _serialize_any(back, path, union_tag, tag_policy, checked=False)

    if _reads_back(Any, instance, written, union_tag, dumps_as=dumps_as):
        for w in within:
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
        return written
    _warn_unread_any(instance, path, "an Any node does not read the spec it would be written as back as an equal value")
    return _serialize_untyped(instance)


def _held_object_form(instance: Any, path: FieldPath, union_tag: str, tag_policy: TagPolicy) -> Any:
    """Return the spec an ``Any`` node reads *instance* back from: a callable's, a struct's, or a leaf.

    A callable is written as a Callable field writes it, a bare path opened into its
    ``bind:`` form, since an ``Any`` node reads a bare string as text; a struct as its
    ``class:`` spec beside its fields; a leaf as :func:`_serialize_leaf` writes it.

    Raises:
        ConfargError: If no spec spells the callable or the struct (:func:`_serialize_callable`,
            :func:`_class_path`).

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """
    if isinstance(instance, (str, int, float, enum.Enum)) or any(isinstance(instance, t) for t in _LEAF_SERIALIZERS):
        return _serialize_leaf(None, instance)
    if callable(instance):
        spec = _serialize_callable(
            instance,
            lambda owner: _serialize_struct(type(owner), owner, path, union_tag, tag_policy),
        )
        return _serialize_untyped(promote_bare_spec(spec) if isinstance(spec, str) else spec)
    cls = type(instance)
    if _is_struct(cls):
        return {_defaults.CLASS_KEY: _class_path(cls), **_serialize_struct(cls, instance, path, union_tag, tag_policy)}
    return _serialize_leaf(None, instance)


def _warn_unread_any(instance: Any, path: FieldPath, reason: str) -> None:
    """Warn that what an ``Any`` node holds at *path* is written untyped, since no spec reads it back.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """
    warnings.warn(
        f"Value at '{_spell_field_path(path) or _defaults.ROOT_KEY}' will not read back as the"
        f" {type(instance).__name__} it holds: {reason.rstrip('.')}. It is written untyped.",
        ConfargWarning,
        stacklevel=2,
    )


def _serialize_collection(
    tp: Any,
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
) -> list[Any]:
    """Serialize a list, set, or frozenset."""
    et = _elem_type(tp)
    if _is_list(tp):
        return [_serialize(et, v, (*path, i), union_tag, tag_policy) for i, v in enumerate(instance)]
    items = [_serialize(et, v, path, union_tag, tag_policy) for v in instance]
    return sorted(items, key=_sort_key)


def _serialize_namedtuple(
    tp: Any,
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
) -> dict[str, Any]:
    """Serialize a namedtuple instance to a dict keyed by field name."""
    flds = _namedtuple_fields(tp)
    out: dict[str, Any] = {}
    for name, ft in flds.items():
        value = getattr(instance, name)
        fp = (*path, name)
        out[name] = _serialize(ft, value, fp, union_tag, tag_policy)
    return out


def _serialize_struct(
    tp: Any,
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
) -> dict[str, Any]:
    """Serialize a dataclass or plain-class instance to a dict."""
    actual_tp = type(instance)
    if actual_tp is not tp and _is_struct(actual_tp) and issubclass(actual_tp, tp):
        out = _serialize_struct(actual_tp, instance, path, union_tag, tag_policy)
        out[union_tag] = _class_path(actual_tp)
        return out
    flds = _struct_fields(tp)
    out: dict[str, Any] = {}
    for name, ft in flds.items():
        try:
            value = getattr(instance, name)
        except AttributeError:
            msg = (
                f"Cannot serialize {type(instance).__name__} at '{_spell_field_path(path) or _defaults.ROOT_KEY}':"
                f" field '{name}' is declared in {type(instance).__name__}.__init__"
                f" but not accessible on the instance as self.{name}."
                f" Plain classes must store every __init__ parameter as a same-named instance attribute."
            )
            raise ConfargError(msg) from None
        fp = (*path, name)
        out[name] = _serialize(ft, value, fp, union_tag, tag_policy)
    return out


def _serialize_union(
    tp: Any,
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
) -> Any:
    """Serialize a Union value, adding a class tag or a force-cast when needed.

    A struct variant is disambiguated by the class tag; a leaf variant whose bare form another
    variant would steal back is written as its ``{__cast__, __value__}`` spelling instead, and
    warns when no cast can name it.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#casting-a-stolen-leaf
    """
    variant_tp = _find_variant_type(tp, instance)
    if variant_tp is None:
        return instance

    serialized = _serialize(variant_tp, instance, path, union_tag, tag_policy)

    if _is_struct_variant(variant_tp):
        if isinstance(serialized, dict) and (tag_policy == "always" or _needs_tag(tp, serialized, union_tag)):
            serialized[union_tag] = _class_path(variant_tp)
        return serialized

    # With one variant beside None, no other variant can take the dump: only a token selects
    # None, and a dump holds none. Reading it back would only build the value again.
    if len(_union_args_no_none(tp)) == 1:
        return serialized
    # The Any variant already wrote what a bare Any field reads back, or warned that nothing
    # does: the union must read the dump back as that Any reading, its cast the dump's own type.
    holds_anything = _holds_anything(variant_tp)
    expected = _any_reading(serialized, union_tag) if holds_anything else instance

    def dumps_as(back: Any) -> Any:
        if holds_anything:
            return _serialize_any(back, path, union_tag, tag_policy, checked=False)
        return _serialize(variant_tp, back, path, union_tag, tag_policy)

    # A callable read back from its spec, an instance, a partial or a bound method, compares
    # equal to nothing but itself: it is the same value when it dumps back as the same spec.
    by_state = dumps_as if holds_anything or _is_callable(variant_tp) else None
    if _reads_back(tp, expected, serialized, union_tag, dumps_as=by_state):
        return serialized
    cast = _cast_dict(type(serialized) if holds_anything else variant_tp, serialized)
    if _reads_back(tp, expected, cast, union_tag, dumps_as=by_state):
        return cast
    _warn_unpinnable_leaf(variant_tp, serialized, path)
    return serialized


def _warn_unpinnable_leaf(variant_tp: Any, serialized: Any, path: FieldPath) -> None:
    """Warn that a leaf no ``__cast__`` can name will read back as another union variant.

    Args:
        variant_tp: The variant the value was serialized as.
        serialized: Its bare serialized form, written as-is.
        path: The field's path below the instance, which diagnostics name.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#casting-a-stolen-leaf
    """
    warnings.warn(
        f"Value at '{_spell_field_path(path) or _defaults.ROOT_KEY}' will not read back as"
        f" {getattr(variant_tp, '__name__', variant_tp)!r}: another union variant takes the"
        f" dumped {type(serialized).__name__}, and no __cast__ names that type."
        f" confarg.register_leaf_type makes it nameable.",
        ConfargWarning,
        stacklevel=2,
    )


def _reads_back(
    tp: Any,
    expected: Any,
    data: Any,
    union_tag: str,
    *,
    dumps_as: Callable[[Any], Any] | None = None,
) -> bool:
    """Check that reading *data* back as *tp* produces *expected*.

    Runs the reader itself instead of modelling a second time what selects a variant, so the
    answer follows whatever decides it — the stealing rule, declaration order or a tag.

    Args:
        tp: The declared type the value would be read back as.
        expected: What reading *data* back must produce: the value that produced it, or, for
            an ``Any`` variant, what a bare ``Any`` field reads *data* back as.
        data: The serialized form to read back.
        union_tag: The field name used as a discriminator tag in unions.
        dumps_as: Serializes a value read back that does not compare equal: an object built
            from a spec, a bound method or a partial is the same value when it holds the same
            state, so dumps back as *data*.

    Returns:
        True if construction yields a value of the same type that compares equal, or that
        *dumps_as* writes as *data*.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#casting-a-stolen-leaf
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """
    try:
        back = construct(tp, data, union_tag=union_tag)
    except (ConfargError, TypeError, ValueError):
        return False
    return type(back) is type(expected) and _same_value(back, expected, data, dumps_as)


def _same_value(back: Any, expected: Any, data: Any, dumps_as: Callable[[Any], Any] | None) -> bool:
    """Return whether *back*, read back from *data*, is the value *expected* (:func:`_reads_back`)."""
    try:
        # `is` first: a value that passes through unchanged round-trips even when it does not
        # compare equal to itself (float('nan')).
        if back is expected or back == expected:
            return True
        if dumps_as is None:
            return False
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConfargWarning)
            return bool(dumps_as(back) == data)
    except (ConfargError, TypeError, ValueError):
        return False


def _any_reading(data: Any, union_tag: str) -> Any:
    """Return what a bare ``Any`` field reads *data* back as, *data* itself when it reads none.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """
    try:
        return construct(Any, data, union_tag=union_tag)
    except (ConfargError, TypeError, ValueError):
        return data


def _serialize_tuple(
    tp: Any,
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
) -> list[Any]:
    """Serialize a tuple to a list."""
    tt = _tuple_types(tp)
    if tt is None:
        et = _elem_type(tp)
        return [_serialize(et, v, (*path, i), union_tag, tag_policy) for i, v in enumerate(instance)]
    return [
        _serialize(et, v, (*path, i), union_tag, tag_policy)
        for i, (et, v) in enumerate(zip(tt, instance, strict=False))
    ]


def _serialize_dict(
    tp: Any,
    instance: Any,
    path: FieldPath,
    union_tag: str,
    tag_policy: TagPolicy,
) -> dict[Any, Any]:
    """Serialize a typed dict."""
    kt, vt = _dict_kv(tp)
    return {
        _data_key(_serialize_leaf(kt, k), (*path, str(k))): _serialize(vt, v, (*path, str(k)), union_tag, tag_policy)
        for k, v in instance.items()
    }


def _data_key(key: Any, path: FieldPath) -> Any:
    """Return the serialized *key*, at *path*, as a data key of the dict ``dump()`` writes.

    The one check both dict writers make, a typed dict's and an ``Any`` node's; a raw dict is a
    document, whose reserved keys are the file's own, and ``_serialize_untyped`` writes it as it stands.

    Raises:
        ConfargError: If *key* is one ``_defaults.RESERVED_KEYS`` lists, which a file reads as its own.

    Dev Notes:
        docs-dev/architecture/config-files/reserved-keys.md#reserved-file-only-keys
    """
    if isinstance(key, str) and key in _defaults.RESERVED_KEYS:
        raise ConfargError.reserved_data_key(key, _spell_field_path(path))
    return key


def _serialize_leaf(tp: Any, value: Any) -> Any:
    """Serialize a leaf value: Enum → .value, registered leaf → its serializer, else passthrough.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    if isinstance(value, _StrToken):
        return str(value)
    if (form := _object_form(value)) is not value:
        return form
    if tp is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, type):
        return _class_path(value)
    return value


def _object_form(value: Any) -> Any:
    """Return the form a file holds an object in: an Enum member's value, a registered leaf's serialized form.

    Any other value is returned as it is, a token included: a token is a str subclass, and
    registering ``str`` must not let one leak out. isinstance, so a token subclass
    (_UnionSeqToken) is caught too; it still spares a caller's own str subclass, which cannot
    inherit from a private type. See docs-dev/architecture/invariants.md#tokens-mean-untyped-text.
    """
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, _StrToken):
        return value
    for leaf_tp, serialize in _LEAF_SERIALIZERS.items():
        # isinstance, not an exact type test: a real Path is a WindowsPath or a PosixPath.
        if isinstance(value, leaf_tp):
            return serialize(value)
    return value


def written_form(value: Any) -> Any:
    """Return *value* as an expression writes it: each Enum member and registered leaf in its dump form.

    What a resolved expression leaves in the data, and what an interpolation stringifies: the
    form :func:`_serialize_leaf` dumps such an object in, never its ``str()``, so ``${c}``
    writes ``red`` and a path its forward slashes. A dict or a list is walked, and copied only
    where something in it changed; anything else is returned as it is.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
    """
    if isinstance(value, dict):
        items = {k: written_form(v) for k, v in value.items()}
        return value if all(items[k] is v for k, v in value.items()) else items
    if isinstance(value, list):
        elements = [written_form(v) for v in value]
        return value if all(a is b for a, b in zip(elements, value, strict=True)) else elements
    return _object_form(value)


def _class_path(cls: type) -> str:
    """Return the dotted path a class is written as, a class tag or a type leaf.

    Raises:
        ConfargError: If the path does not import back as *cls* (:func:`imports_back`), as for a
            class defined in a function or a name its module rebinds.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back
    """
    path = dotted_name(cls)
    if not imports_back(path, cls):
        msg = (
            f"Cannot serialize class {cls!r}: {path!r} does not import back as it. A class defined"
            " in a function, or one its module no longer holds under that name, has no dotted path."
        )
        raise ConfargError(msg)
    return path


def _serialize_untyped(value: Any) -> Any:
    """Serialize a raw merged dict: containers recursed, leaves through _serialize_leaf.

    The counterpart of :func:`_serialize` for data that carries no declared types
    (the dict accepted by ``dump_file``), so only the type-less leaf rules apply:
    ``Enum`` becomes its value, ``Path`` a string, ``_StrToken`` a plain ``str``.
    An ``int`` is never widened to ``float`` — nothing here says it should be one.

    A force-cast is written back as the ``{__cast__, __value__}`` dict a file spells it
    with, rather than as the value it pins: nothing here knows the declared type, and a
    bare scalar is re-read by declaration order. A list op the merge still holds is written
    as the plain reserved key a file writes it with (``__append__``, ``__base__``, ...), and a
    delete as the file's node delete: a key delete as ``{__unset__: true}``, a deleted base
    (``{ListOp.BASE: DICT_DELETE}``) as ``__unset__: true`` beside the node's other keys.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    if isinstance(value, _Pinned):
        return _serialize_pinned(value)
    if isinstance(value, _DeleteSentinel):
        return {_defaults.UNSET_KEY: True}
    if isinstance(value, dict) and isinstance(value.get(ListOp.BASE), _DeleteSentinel):
        rest = {k: v for k, v in value.items() if k is not ListOp.BASE}
        return {_defaults.UNSET_KEY: True, **_serialize_untyped(rest)}
    if isinstance(value, dict):
        return {(str(k) if isinstance(k, ListOp) else k): _serialize_untyped(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_untyped(v) for v in value]
    return _serialize_leaf(None, value)


def _serialize_pinned(pin: _Pinned) -> dict[str, Any]:
    """Write a force-cast as the ``{__cast__, __value__}`` dict ``_try_pinned_dict`` reads back.

    The pinned value goes back through :func:`_serialize_untyped`, which unwraps the
    ``_StrToken`` a CLI cast pins and walks a container a file cast may hold.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#cast-pinning-in-files
    """
    return _cast_dict(pin.tp, _serialize_untyped(pin.value))


def _cast_dict(tp: Any, value: Any) -> dict[str, Any]:
    """Spell *value* in the ``{__cast__, __value__}`` form ``_try_pinned_dict`` reads back.

    Args:
        tp: The type the value is pinned to.
        value: The already-serialized value.

    Returns:
        The two-key cast dict.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#cast-pinning-in-files
    """
    return {_defaults.CAST_KEY: cast_name_for_type(tp), _defaults.VALUE_KEY: value}


def _find_variant_type(tp: Any, instance: Any) -> Any | None:
    """Find which Union variant the instance belongs to, in declaration order, ``Any`` last.

    ``Any`` holds every instance, so it is asked after every other variant, as construction
    offers it a value only after every other variant refused it.

    Dev Notes:
        docs-dev/architecture/types/construction.md#an-any-variant-is-tried-last
    """
    args = [_resolve_type(arg) for arg in _union_args_no_none(tp)]
    for arg in sorted(args, key=_holds_anything):
        if _variant_holds(arg, instance):
            return arg
    return None


def _variant_holds(tp: Any, instance: Any) -> bool:  # noqa: PLR0911  # one return per kind
    """True if *instance* is a value of union variant *tp*.

    Dispatches on :func:`_type_kind`, as :func:`_serialize_by_type` does, so the variant
    chosen here is the one that then serializes the value. A bare ``isinstance``
    cannot ask: a parameterized generic and a ``Literal`` both refuse to be its second
    argument, which left every union holding one undumpable. Each shape answers with the
    concrete class construction builds for it -- ``list`` for ``Sequence[X]``, ``dict`` for
    ``Mapping[K, V]`` -- and a ``Literal`` answers by membership, so ``True`` is not a value
    of ``Literal[1]``.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    match _type_kind(tp):
        case _TypeKind.NAMEDTUPLE | _TypeKind.STRUCT:
            return isinstance(instance, tp)
        case _TypeKind.LIST:
            return isinstance(instance, list)
        case _TypeKind.SET:
            return isinstance(instance, set)
        case _TypeKind.FROZENSET:
            return isinstance(instance, frozenset)
        case _TypeKind.TUPLE:
            fixed = _fixed_seq_types(tp)
            return isinstance(instance, tuple) and (fixed is None or len(instance) == len(fixed))
        case _TypeKind.DICT:
            return isinstance(instance, dict)
        case _TypeKind.LEAF if _is_literal(tp):
            return any(type(m) is type(instance) and m == instance for m in _literal_values(tp))
        case _TypeKind.ANY:
            return True
        case _TypeKind.UNION | _TypeKind.TAGGABLE_LEAF | _TypeKind.CALLABLE | _TypeKind.LEAF:
            # What is left is a class, or is parameterized over one (``type[X]``,
            # ``Callable[..., X]``).
            origin = _origin(tp)
            checkable = origin if isinstance(origin, type) else tp
            return isinstance(checkable, type) and isinstance(instance, checkable)


def _needs_tag(tp: Any, serialized_data: MergeDict, union_tag: str) -> bool:
    """Check if a class tag is needed by running disambiguation on the serialized data."""
    struct_vars = [v for v in _union_args_no_none(tp) if _is_struct_variant(_resolve_type(v))]
    if len(struct_vars) <= 1:
        return False
    matches = _disambiguate_struct(struct_vars, serialized_data, union_tag)
    return len(matches) != 1


def _sort_key(value: Any) -> tuple[str, str]:
    """Sort key for heterogeneous set/frozenset serialization."""
    return (type(value).__name__, str(value))

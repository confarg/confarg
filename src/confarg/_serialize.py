# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Serialization of dataclass instances to plain dicts (the inverse of construction).

Dev Notes:
    docs-dev/architecture/types/serialization.md#serialization
"""

from __future__ import annotations

import contextlib
import enum
import inspect
import math
import warnings
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any, cast

from confarg import _defaults
from confarg._callable import (
    _serialize_callable,
    _SpecWriter,
    holds_an_opener,
    promote_bare_spec,
    refuse_a_field_spelling_an_object_opener,
)
from confarg._cast import cast_name_for_type
from confarg._depth import MAX_DEPTH, refuse_overflow
from confarg._import import dotted_name, imports_back
from confarg._merge import ListOp, MergeDict, _DeleteSentinel, _key_spelling
from confarg._types import (
    TagPolicy,
    _class_of,
    _demands_tag,
    _dict_kv,
    _elem_type,
    _init_params,
    _is_callable,
    _is_dc,
    _is_list,
    _is_literal,
    _is_struct,
    _is_type_ref,
    _is_union,
    _literal_members,
    _literal_values,
    _namedtuple_fields,
    _Pinned,
    _registration_key,
    _resolve_type,
    _spell_type,
    _StrToken,
    _struct_state_fields,
    _tagged_struct,
    _tuple_types,
    _union_args,
    _union_args_no_none,
)
from confarg.exceptions import ConfargError, ConfargWarning, FieldPath, _spell_field_path, _spelled_where
from confarg.typedload._coerce import (
    _LEAF_SERIALIZERS,
    _is_coercible_leaf,
    _is_struct_variant,
    _refuse_a_forbidden_literal,
    _registered_leaf_of,
    _type_kind,
    _TypeKind,
)
from confarg.typedload._construct import _disambiguate_struct, _spell_key, construct, read_key
from confarg.typedload._holding import _find_variant_type, _holds, _holds_anything, _literal_holds, _variant_holds

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable


@dataclass(frozen=True)
class _DumpOptions:
    """The options of one dump, which every serializer passes down as they are."""

    tag_policy: TagPolicy
    """``"auto"`` (tag only when needed) or ``"always"`` (tag every union member)."""
    native_types: tuple[type, ...] = ()
    """The registered leaf types written as the objects they are, not as their serialized form."""
    action: str = "dump the value"
    """What the dump is, for a refusal: ``dump Config``."""
    open_at: dict[int, FieldPath] = field(default_factory=dict, compare=False)
    """The id of each value being serialized, on the path to the one being serialized now, and its position."""


def _open(instance: Any, path: FieldPath, opts: _DumpOptions) -> bool:
    """Enter *instance* at *path*: refuse it past the bound or below itself, and return whether it was opened here.

    The depth is the length of *path*. The same instance entered again at its own position (a
    union serializing it as its variant) is no cycle, and was opened by the first entry.

    Raises:
        ConfargError: If *path* is deeper than ``_depth.MAX_DEPTH``, or *instance* is a value
            being serialized above it, which contains itself.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#a-configuration-nests-at-most-64-levels
    """
    if len(path) > MAX_DEPTH:
        raise ConfargError.too_deep(opts.action, path, MAX_DEPTH)
    holder = opts.open_at.get(id(instance))
    if holder is None:
        opts.open_at[id(instance)] = path
        return True
    if len(holder) < len(path):
        raise ConfargError.holds_itself(opts.action, path, holder)
    return False


def _untyped_at(value: Any, path: FieldPath, opts: _DumpOptions) -> Any:
    """Serialize *value*, which a typed dump writes with no declared type, counted from *path*.

    :func:`_serialize_untyped` threads no path, so the value is counted once, where it is written.
    """
    refuse_overflow(value, opts.action, at=path)
    return _serialize_untyped(value, opts.native_types)


def _check_native_types(native_types: Iterable[type]) -> tuple[type, ...]:
    """Return *native_types* as a tuple of the registered leaf types they read through.

    A parameterized form names the class whose registration reads it (:func:`_registration_key`),
    so ``re.Pattern[str]`` keeps a pattern as ``re.Pattern`` does: the dump looks a value up by
    its class.

    Raises:
        TypeError: If one is no registered leaf type: nothing else is serialized to a form
            it could be kept from.
    """
    native = tuple(native_types)
    for tp in native:
        if _registration_key(tp) not in _LEAF_SERIALIZERS:
            msg = f"native_types names {_spell_type(tp, as_written=True)}, which is no registered leaf type"
            raise TypeError(msg)
    return tuple(_registration_key(tp) for tp in native)


def _serialize(
    tp: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
) -> Any:
    """Serialize a typed value to a plain dict/list/leaf structure.

    Args:
        tp: The declared type of the value.
        instance: The value to serialize.
        path: The field's path below the instance, which diagnostics name.
        opts: The options of the dump.

    Returns:
        A structure of dicts, lists and leaves: each leaf a value every config writer holds,
        or an object whose registered type ``opts.native_types`` names. A value *tp* does not
        hold is written as an ``Any`` node writes it, with a :class:`ConfargWarning`
        (:func:`_serialize_foreign`).
    """
    tp = _resolve_type(tp)
    if instance is not None:
        _refuse_an_undumpable_type(tp, path)
    if not _holds(tp, instance):
        return _serialize_foreign(tp, instance, path, opts)
    if instance is None:
        return None
    opened = _open(instance, path, opts)
    try:
        return _serialize_by_type(tp, instance, path, opts)
    finally:
        if opened:
            del opts.open_at[id(instance)]


def _serialize_by_type(  # noqa: PLR0911  # one return per kind
    tp: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
) -> Any:
    """Dispatch serialization on the shape :func:`_type_kind` names, after None is handled."""
    match _type_kind(tp):
        case _TypeKind.UNION:
            return _serialize_union(tp, instance, path, opts)
        case _TypeKind.NAMEDTUPLE:
            return _serialize_namedtuple(tp, instance, path, opts)
        case _TypeKind.STRUCT:
            return _serialize_declared_struct(tp, instance, path, opts)
        case _TypeKind.LIST | _TypeKind.SET | _TypeKind.FROZENSET:
            return _serialize_collection(tp, instance, path, opts)
        case _TypeKind.TUPLE:
            return _serialize_tuple(tp, instance, path, opts)
        case _TypeKind.DICT:
            return _serialize_dict(tp, instance, path, opts)
        case _TypeKind.CALLABLE:
            return _serialize_callable(instance, path, _spec_writer(opts))
        case _TypeKind.ANY:
            return _serialize_any(instance, path, opts)
        case _TypeKind.TAGGABLE_LEAF | _TypeKind.LEAF:
            _refuse_an_unread_literal_member(tp, instance, path)
            return _serialize_read_leaf(tp, instance, path, opts)


def _refuse_an_undumpable_type(tp: Any, path: FieldPath) -> None:
    """Refuse to write any value at *path* when its declared type *tp* is one construction does not build.

    Asked before what the value is: a leaf :func:`_refuse_an_unsupported_leaf` refuses, or a
    union holding a ``Literal`` member no value reads as.

    Raises:
        ConfargError: If *tp* is such a type.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-unsupported-leaf-is-refused-both-ways
    """
    match _type_kind(tp):
        case _TypeKind.TAGGABLE_LEAF | _TypeKind.LEAF:
            _refuse_an_unsupported_leaf(tp, path)
        case _TypeKind.UNION:
            _refuse_a_forbidden_literal(tp, _spell_field_path(path))
        case _:
            pass


def _serialize_foreign(tp: Any, instance: Any, path: FieldPath, opts: _DumpOptions) -> Any:
    """Write *instance*, which its declared type *tp* does not hold, as an ``Any`` node writes it, and warn.

    The form is the spec an ``Any`` node rebuilds it from (:func:`_serialize_any`), else the
    value untyped, when no spec spells it.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it
    """
    # A class is named itself, not by its metaclass: "its class int", never "its type".
    held = f"class {instance.__name__}" if isinstance(instance, type) else type(instance).__name__
    warnings.warn(
        f"Value at {_spelled_where(path)} will not read back: its"
        f" {held} is no value of {_spell_type(tp)}, the type it is"
        " declared as. It is written as an Any field holds it.",
        ConfargWarning,
        stacklevel=3,
    )
    if instance is None:
        return None
    try:
        return _serialize_any(instance, path, opts, checked=False)
    except ConfargError:
        return _untyped_at(instance, path, opts)


def _refuse_an_unsupported_leaf(tp: Any, path: FieldPath) -> None:
    """Refuse to write a value at *path* typed by *tp* when *tp* is a leaf construction does not build.

    Raises:
        ConfargError: If *tp* is neither a type reference nor a leaf :func:`_is_coercible_leaf` names.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-unsupported-leaf-is-refused-both-ways
    """
    resolved = _resolve_type(tp)
    where = _spell_field_path(path)
    _refuse_a_forbidden_literal(resolved, where)
    if _is_type_ref(resolved) or _is_coercible_leaf(resolved):
        return
    name = _spell_type(resolved)
    msg = (
        f"Cannot serialize {name} at {_spelled_where(where)}: {name} is no leaf type"
        f" confarg reads, so the value would not load back."
        f" confarg.register_leaf_type({_spell_type(_registration_key(resolved))}, ...) makes it one."
    )
    raise ConfargError(msg)


def _refuse_an_unread_literal_member(tp: Any, instance: Any, path: FieldPath) -> None:
    """Refuse to write *instance* at *path* when it is a member of the Literal *tp* that confarg reads nowhere.

    A bytes member, which PEP 586 allows: it is refused as a ``bytes`` field's value is, since
    the dump would not load back.

    Raises:
        ConfargError: If *instance* is a member of *tp* that no value reads as.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-literal-member-is-what-pep-586-allows.md#a-literal-member-is-what-pep-586-allows
    """
    if not _is_literal(tp) or _literal_holds(_literal_values(tp), instance):
        return
    if _literal_holds(_literal_members(tp), instance):
        msg = (
            f"Cannot serialize {instance!r} at {_spelled_where(path)}: it is a"
            f" {type(instance).__name__} member, which confarg reads no value as, so the value would not load back."
        )
        raise ConfargError(msg)


def _serialize_any(
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
    *,
    checked: bool = True,
) -> Any:
    """Serialize what an ``Any`` node holds by its runtime type, as the spec that rebuilds it.

    A dict and a list are walked, each item an ``Any`` node in turn; a tuple or a set is
    written as the list a file holds. Any other value is written by :func:`_held_object_form`.

    *checked*, each value is kept only when an ``Any`` node reads it back as the value it
    came from (:func:`_reads_back`), an object compared by the state it holds; any other is
    written untyped (:func:`_serialize_untyped`), with a :class:`ConfargWarning` saying why.
    A dict holding an opener key, which reads back as a spec, a key that does not read back
    (:func:`_warn_an_unread_key`), and a tuple or a set, which reads back as a list, warn too.
    Unchecked, the form is returned as it is, and a value no spec can write raises.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """

    def item(value: Any, key: str | int) -> Any:
        if value is None:
            return None
        return _serialize_any(value, (*path, key), opts, checked=checked)

    opened = _open(instance, path, opts)
    try:
        return _serialize_any_form(instance, path, opts, item, checked=checked)
    finally:
        if opened:
            del opts.open_at[id(instance)]


def _serialize_any_form(
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
    item: Callable[[Any, str | int], Any],
    *,
    checked: bool,
) -> Any:
    """Return what :func:`_serialize_any` writes *instance* as, each item written by *item*."""
    if isinstance(instance, dict):
        out = _written_dict(Any, instance, path, opts, item, checked=checked)
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
        return _serialize_held_object(instance, path, opts)
    return _held_object_form(instance, path, opts)


def _serialize_held_object(instance: Any, path: FieldPath, opts: _DumpOptions) -> Any:
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
            written = _held_object_form(instance, path, opts)
        except ConfargError as e:
            unwritable = e
    if unwritable is not None:
        _warn_unread_any(instance, path, str(unwritable))
        return _untyped_at(instance, path, opts)

    def dumps_as(back: Any) -> Any:
        return _serialize_any(back, path, opts, checked=False)

    if _reads_back(Any, instance, written, dumps_as=dumps_as):
        for w in within:
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
        return written
    _warn_unread_any(instance, path, "an Any node does not read the spec it would be written as back as an equal value")
    return _untyped_at(instance, path, opts)


def _held_object_form(instance: Any, path: FieldPath, opts: _DumpOptions) -> Any:
    """Return the spec an ``Any`` node reads *instance* back from: a callable's, a struct's, or a leaf.

    A callable is written as a Callable field writes it, a bare path opened into its
    ``bind:`` form, since an ``Any`` node reads a bare string as text; a struct as the spec
    the class key opens beside its fields; a leaf as :func:`_serialize_leaf` writes it.

    Raises:
        ConfargError: If no spec spells the callable or the struct (:func:`_serialize_callable`,
            :func:`_class_path`, a struct field spelled like an object opener), or the value is
            of a leaf construction does not build
            (:func:`_refuse_an_unsupported_leaf`).

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """
    cls = type(instance)
    a_leaf = _registered_leaf_of(instance) is not None and (callable(instance) or not _is_struct(cls))
    if a_leaf or isinstance(instance, (str, int, float, enum.Enum)):
        return _serialize_leaf(None, instance, opts.native_types)
    if callable(instance):
        spec = _serialize_callable(instance, path, _spec_writer(opts))
        return promote_bare_spec(spec) if isinstance(spec, str) else spec
    if _is_struct(cls):
        return _tagged_spec(cls, instance, path, opts)
    _refuse_an_unsupported_leaf(cls, path)
    return _serialize_leaf(None, instance, opts.native_types)


def _spec_writer(opts: _DumpOptions) -> _SpecWriter:
    """Return how a callable's spec writes what it holds in this dump.

    A callable instance, or a method's owner, is a struct, its fields written as their types
    say; an argument is written as the parameter it fills is typed
    (:func:`~confarg._callable.argument_types`), as a field of that type is.

    Dev Notes:
        docs-dev/architecture/callables.md#round-trip
    """
    return _SpecWriter(
        fields=lambda owner, at: _serialize_struct(type(owner), owner, at, opts),
        argument=lambda tp, value, at: _serialize(tp, value, at, opts),
    )


def _tagged_spec(cls: type, instance: Any, path: FieldPath, opts: _DumpOptions) -> dict[str, Any]:
    """Return the struct *instance* of class *cls* as the class key beside its fields.

    Raises:
        ConfargError: If *cls* has no dotted path (:func:`_class_path`), or a field is spelled
            like an object opener.
    """
    fields = _serialize_struct(cls, instance, path, opts)
    refuse_a_field_spelling_an_object_opener(fields, cls, "its", _defaults.CLASS_KEY)
    return {_defaults.CLASS_KEY: _class_path(cls), **fields}


def _warn_unread_any(instance: Any, path: FieldPath, reason: str) -> None:
    """Warn that what an ``Any`` node holds at *path* is written untyped, since no spec reads it back.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
    """
    warnings.warn(
        f"Value at {_spelled_where(path)} will not read back as the"
        f" {type(instance).__name__} it holds: {reason.rstrip('.')}. It is written untyped.",
        ConfargWarning,
        stacklevel=2,
    )


def _serialize_collection(
    tp: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
) -> list[Any]:
    """Serialize a list, set, or frozenset."""
    et = _elem_type(tp)
    if _is_list(tp):
        return [_serialize(et, v, (*path, i), opts) for i, v in enumerate(instance)]
    items = [_serialize(et, v, path, opts) for v in instance]
    return sorted(items, key=_sort_key)


def _serialize_namedtuple(
    tp: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
) -> dict[str, Any]:
    """Serialize a namedtuple instance to a dict keyed by field name."""
    flds = _namedtuple_fields(tp)
    out: dict[str, Any] = {}
    for name, ft in flds.items():
        value = getattr(instance, name)
        fp = (*path, name)
        out[name] = _serialize(ft, value, fp, opts)
    return out


def _serialize_declared_struct(tp: Any, instance: Any, path: FieldPath, opts: _DumpOptions) -> dict[str, Any]:
    """Serialize a struct instance where *tp* is declared: the fields of the class it is written as, and its tag.

    It is tagged where reading back needs the tag: an instance of a subclass, and any instance
    of a struct that demands its tag (:func:`_demands_tag`), its own class's included.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    written = _written_struct(tp, instance)
    out = _serialize_struct(written, instance, path, opts)
    if written is not tp or _demands_tag(tp):
        _write_tag(written, out)
    return out


def _serialize_struct(
    tp: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
) -> dict[str, Any]:
    """Serialize the members a dataclass or plain-class instance holds as the struct *tp*, writing no tag."""
    flds = _struct_state_fields(tp)
    out: dict[str, Any] = {}
    for name, ft in flds.items():
        try:
            value = _held_attribute(instance, name)
        except _NotHeldError as e:
            raise _unheld_member_error(tp, instance, path, name, class_attribute=e.class_attribute) from None
        fp = (*path, name)
        out[name] = _serialize(ft, value, fp, opts)
    return out


def _written_struct(tp: Any, instance: Any) -> Any:
    """Return the struct *instance* is written as where *tp* is declared, *tp* itself or the instance's own class.

    Its own class, when a tag naming it builds where *tp* is declared, is written with that tag
    (:func:`_write_tag`), by the struct and by a union alike.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    actual_tp = type(instance)
    if actual_tp is _class_of(tp) or not _is_struct(actual_tp):
        return tp
    bound = _tagged_struct(actual_tp, tp)
    return tp if bound is None else bound


def _write_tag(written: Any, out: dict[str, Any]) -> None:
    """Write into *out*, an instance's fields, the class key naming the class of *written*, the struct it is written as.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    out[_defaults.CLASS_KEY] = _class_path(_class_of(written))


class _NotHeldError(AttributeError):
    """The instance holds no value under a member's name; *class_attribute* if only its class spells one."""

    def __init__(self, name: str, *, class_attribute: bool) -> None:
        super().__init__(name)
        self.class_attribute = class_attribute


def _held_attribute(instance: Any, name: str) -> Any:
    """Return the value *instance* holds as *name*: an instance attribute, a slot, a descriptor's or ``__getattr__``'s.

    A plain class attribute is the class's value, not the instance's, so it is not held.

    Raises:
        _NotHeldError: If the instance holds nothing under *name*.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-object-dump-writes-state.md#a-plain-class-dumps-the-parameters-it-holds
    """
    try:
        static = inspect.getattr_static(instance, name)
    except AttributeError:
        # Nothing static spells it, so only the instance's own __getattr__ can answer.
        try:
            return getattr(instance, name)
        except AttributeError:
            raise _NotHeldError(name, class_attribute=False) from None
    own = getattr(instance, "__dict__", None)
    if not (isinstance(own, dict) and name in own) and not hasattr(type(static), "__get__"):
        raise _NotHeldError(name, class_attribute=True)
    try:
        return getattr(instance, name)
    except AttributeError:
        raise _NotHeldError(name, class_attribute=False) from None


def _unheld_member_error(tp: Any, instance: Any, path: FieldPath, name: str, *, class_attribute: bool) -> ConfargError:
    """Return the refusal to dump *instance*, which does not hold its member *name*.

    A dataclass field set through a descriptor with no ``__get__`` is named as such: it was
    set, and nothing reads it back.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-descriptor-typed-field-takes-what-its-__set__-takes
    """
    cls_name = type(instance).__name__
    where = f"Cannot serialize {cls_name} at {_spelled_where(path)}:"
    if _is_dc(tp):
        static = type(inspect.getattr_static(type(instance), name, None))
        if hasattr(static, "__set__") and not hasattr(static, "__get__"):
            return ConfargError(
                f"{where} field '{name}' of {cls_name} is set through its descriptor {static.__name__}, "
                "which has no __get__ to read it back.",
            )
        return ConfargError(f"{where} field '{name}' of {cls_name} is not set on the instance.")
    constructor = getattr(_init_params(tp).constructor, "__name__", "__init__")
    held = (
        f"only the class attribute {cls_name}.{name} is set, not one on the instance"
        if class_attribute
        else f"not accessible on the instance as self.{name}"
    )
    return ConfargError(
        f"{where} field '{name}' is declared in {cls_name}.{constructor} but {held}."
        f" Plain classes must store every {constructor} parameter as a same-named instance attribute.",
    )


def _serialize_union(
    tp: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
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
        return _serialize_foreign(tp, instance, path, opts)

    if _is_struct_variant(variant_tp):
        # The union, not the variant, reads the key: it alone answers whether a tag selects.
        written = _written_struct(variant_tp, instance)
        out = _serialize_struct(written, instance, path, opts)
        if opts.tag_policy == "always" or written is not variant_tp or _needs_tag(tp, variant_tp, out):
            _write_tag(written, out)
        return out

    serialized = _serialize(variant_tp, instance, path, opts)

    # With one variant beside None, no other variant can take the dump: only a token selects
    # None, and a dump holds none. Reading it back would only build the value again.
    if len(_union_args_no_none(tp)) == 1:
        return serialized
    return _pinned_to_its_variant(tp, variant_tp, instance, serialized, path=path, opts=opts)


def _pinned_to_its_variant(  # noqa: PLR0913  # the union's question, asked of what its variant wrote
    tp: Any,
    variant_tp: Any,
    instance: Any,
    serialized: Any,
    *,
    path: FieldPath,
    opts: _DumpOptions,
) -> Any:
    """Return *serialized*, which the union *tp*'s *variant_tp* wrote, in the form *tp* reads back as that variant.

    Bare if it reads back so, else cast, and bare with a :class:`ConfargWarning` when only
    another variant reads it.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#casting-a-stolen-leaf
    """
    # The Any variant already wrote what a bare Any field reads back, or warned that nothing
    # does: the union must read the dump back as that Any reading, its cast the dump's own type.
    holds_anything = _holds_anything(variant_tp)
    reads_its_own = holds_anything or not _variant_holds(variant_tp, instance)
    expected = _variant_reading(variant_tp, serialized) if reads_its_own else instance

    def dumps_as(back: Any) -> Any:
        if holds_anything:
            return _serialize_any(back, path, opts, checked=False)
        return _serialize(variant_tp, back, path, opts)

    def is_own(back: Any) -> bool:
        return _find_variant_type(tp, back) == variant_tp

    # An Any variant holds every value, so only the class says the reading is its own. Any other
    # is the variant the union would write what it read back as: a subclass reads back as its parent.
    own = None if holds_anything else is_own
    # A callable read back from its spec, an instance, a partial or a bound method, compares
    # equal to nothing but itself: it is the same value when it dumps back as the same spec.
    by_state = dumps_as if holds_anything or _is_callable(variant_tp) or not _equality_answers(instance) else None
    if _reads_back(tp, expected, serialized, dumps_as=by_state, own=own):
        return serialized
    cast = _cast_dict(type(serialized) if holds_anything else variant_tp, serialized)
    if _reads_back(tp, expected, cast, dumps_as=by_state, own=own):
        return cast
    # A variant that cannot read its own form has said so, at the leaf: no other variant took it.
    if _reads_back(variant_tp, expected, serialized, dumps_as=by_state, own=lambda _: True):
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
        f"Value at {_spelled_where(path)} will not read back as"
        f" {_spell_type(variant_tp)}: another union variant takes the"
        f" dumped {type(serialized).__name__}, and no __cast__ names that type."
        f" confarg.register_leaf_type makes it nameable.",
        ConfargWarning,
        stacklevel=2,
    )


def _reads_back(
    tp: Any,
    expected: Any,
    data: Any,
    *,
    dumps_as: Callable[[Any], Any] | None = None,
    own: Callable[[Any], bool] | None = None,
) -> bool:
    """Check that reading *data* back as *tp* produces *expected*.

    Runs the reader itself instead of modelling a second time what selects a variant, so the
    answer follows whatever decides it — the stealing rule, declaration order or a tag.

    Args:
        tp: The declared type the value would be read back as.
        expected: What reading *data* back must produce: the value that produced it, or, for
            an ``Any`` variant or one holding the value only widened, what a field of that
            variant reads *data* back as.
        data: The serialized form to read back.
        dumps_as: Serializes a value read back that does not compare equal: an object built
            from a spec, a bound method or a partial is the same value when it holds the same
            state, so dumps back as *data*.
        own: Answers whether what is read back is the reading asked for, in place of its being
            of *expected*'s class; the class is asked when omitted.

    Returns:
        True if construction yields a value of the same type, or one *own* accepts, that
        compares equal, or that *dumps_as* writes as *data*. False when reading *data* raises
        anything.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#casting-a-stolen-leaf
        docs-dev/architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it
        docs-dev/architecture/types/serialization.md#a-failing-read-back-leaves-the-dump-whole
    """
    try:
        back = _read_quietly(lambda: construct(tp, data))
    except Exception:  # noqa: BLE001  # a reader may raise anything: the dump finishes
        return False
    is_own = type(back) is type(expected) if own is None else own(back)
    return is_own and _same_value(back, expected, data, dumps_as)


def _read_quietly(read: Callable[[], Any]) -> Any:
    """Return what *read* reads, without the warnings construction gives of what it builds."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConfargWarning)
        return read()


def _same_value(back: Any, expected: Any, data: Any, dumps_as: Callable[[Any], Any] | None) -> bool:
    """Return whether *back*, read back from *data*, is the value *expected* (:func:`_reads_back`).

    It is when the two compare equal, or are both a float NaN. Otherwise, a value of *expected*'s
    class is when *dumps_as* writes it as *data*; an ``==`` that raises answers nothing, and
    leaves this to decide.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-failing-read-back-leaves-the-dump-whole
    """
    # `is` first: a value that passes through unchanged round-trips even when it does not
    # compare equal to itself.
    with contextlib.suppress(Exception):
        if back is expected or back == expected:
            return True
    if _is_nan(back) and _is_nan(expected):
        return True
    if dumps_as is None or type(back) is not type(expected):
        return False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConfargWarning)
            return bool(dumps_as(back) == data)
    except Exception:  # noqa: BLE001  # a value's own == may raise anything: the dump finishes
        return False


def _equality_answers(value: Any) -> bool:
    """Return whether ``==`` tells *value* from another: its class defines it, and it equals itself without raising.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-leaf-is-asked-whether-it-reads-back
    """
    try:
        return type(value).__eq__ is not object.__eq__ and bool(value == value)  # noqa: PLR0124  # NaN is the question
    except Exception:  # noqa: BLE001  # a value's own == may raise anything: the dump finishes
        return False


def _variant_reading(variant_tp: Any, data: Any) -> Any:
    """Return what a field of the union variant *variant_tp* reads *data* back as, *data* itself when it reads none.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-widened-value-reads-back-as-its-variant-reads-it
    """
    try:
        return _read_quietly(lambda: construct(variant_tp, data))
    except Exception:  # noqa: BLE001  # a reader may raise anything: the dump finishes
        return data


def _serialize_read_leaf(tp: Any, instance: Any, path: FieldPath, opts: _DumpOptions) -> Any:
    """Write the leaf *instance* of declared type *tp* in a form that reads back, or warn that none does.

    An unregistered subclass of a registered leaf is written as its class tag, which keeps the
    class its parent's serializer would lose, and any other value as its form. A value whose
    form does not read back is written as its tag if that does, else as its form, with a
    :class:`ConfargWarning` saying what comes back.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-leaf-is-asked-whether-it-reads-back
    """
    written = _serialize_leaf(tp, instance, opts.native_types)
    reading = _what_reading_answers(
        lambda: construct(tp, written),
        instance,
        written,
        lambda back: _serialize_leaf(tp, back, opts.native_types),
        it="it",
    )
    if reading is not None or _is_a_registered_leafs_subclass(instance):
        tag = _reading_tag(tp, instance, path, opts)
        if tag is not None:
            return tag
    if reading is not None:
        warnings.warn(
            f"Value at {_spelled_where(path)} will not read back as"
            f" {_spell_type(type(instance))}: {_spell_type(tp)} {reading}.",
            ConfargWarning,
            stacklevel=2,
        )
    return written


def _is_a_registered_leafs_subclass(value: Any) -> bool:
    """Return whether *value* is registered only through an ancestor, whose serializer would write it."""
    leaf_tp = _registered_leaf_of(value)
    return leaf_tp is not None and leaf_tp is not type(value)


def _reading_tag(tp: Any, instance: Any, path: FieldPath, opts: _DumpOptions) -> dict[str, Any] | None:
    """Return *instance* as its class tag when a *tp* position reads the tag back as it, None otherwise.

    What the fields warn belongs to the tag, so it is said only if the tag is kept. A class
    whose state cannot be read has no tag.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-leaf-is-asked-whether-it-reads-back
    """
    cls = type(instance)
    if not _is_struct(cls):
        return None
    with warnings.catch_warnings(record=True) as within:
        warnings.simplefilter("always", ConfargWarning)
        try:
            tag = _tagged_spec(cls, instance, path, opts)
        except Exception:  # noqa: BLE001  # a class's state may raise anything: its form is what is left
            return None
    if not _reads_back(tp, instance, tag, dumps_as=lambda back: _tagged_spec(cls, back, path, opts)):
        return None
    for w in within:
        warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
    return tag


def _what_reading_answers(  # noqa: PLR0913  # the one question a value and a key share
    read: Callable[[], Any],
    value: Any,
    data: Any,
    dumps_as: Callable[[Any], Any],
    *,
    it: str,
    held: bool = True,
) -> str | None:
    """Return what reading *data* back answers, in the words of a warning, or None if it is *value* again.

    Args:
        read: Reads *data* back.
        value: What the reading must give (:func:`_same_value`).
        data: The written form.
        dumps_as: Serializes what is read back.
        it: What is read, as the warning names it.
        held: Whether the type holds *value*; if not, no reading gives it back.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-failing-read-back-leaves-the-dump-whole
    """
    try:
        back = _read_quietly(read)
    except (ConfargError, TypeError, ValueError):
        return f"refuses {it}"
    except Exception as e:  # noqa: BLE001  # a reader may raise anything: the dump finishes, and says what it was
        return f"refuses {it} ({type(e).__name__}: {e})"
    if held and _same_value(back, value, data, None if _equality_answers(value) else dumps_as):
        return None
    return f"reads {it} as {_spell_key(back)}"


def _serialize_tuple(
    tp: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
) -> list[Any]:
    """Serialize a tuple to a list."""
    tt = _tuple_types(tp)
    if tt is None:
        et = _elem_type(tp)
        return [_serialize(et, v, (*path, i), opts) for i, v in enumerate(instance)]
    return [_serialize(et, v, (*path, i), opts) for i, (et, v) in enumerate(zip(tt, instance, strict=False))]


def _serialize_dict(
    tp: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
) -> dict[Any, Any]:
    """Serialize a typed dict, warning of a key that does not read back (:func:`_written_dict`).

    Raises:
        ConfargError: If it holds a key, and its key type is one construction does not coerce a
            key to, or two keys that are written alike.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-unsupported-leaf-is-refused-both-ways
    """
    kt, vt = _dict_kv(tp)
    rkt = _resolve_type(kt)
    union = _is_union(rkt)
    if instance and not all(_is_coercible_leaf(v) for v in (_union_args(rkt) if union else [rkt])):
        where = _spell_field_path(path)
        msg = (
            f"Cannot serialize {_spell_type(kt)} keys at {_spelled_where(where)}: construction reads no key as one,"
            " so the dict would not load back."
        )
        raise ConfargError(msg)
    return _written_dict(kt, instance, path, opts, lambda v, k: _serialize(vt, v, (*path, k), opts))


def _written_dict(  # noqa: PLR0913  # the one walk both dict writers share
    kt: Any,
    instance: Any,
    path: FieldPath,
    opts: _DumpOptions,
    item: Callable[[Any, str], Any],
    *,
    checked: bool = True,
) -> dict[Any, Any]:
    """Return *instance*, a dict keyed by *kt*, as the dict ``dump()`` writes, each value written by *item*.

    *checked*, a key that does not read back warns (:func:`_warn_an_unread_key`).

    Raises:
        ConfargError: If two keys are written alike, or one is a key ``_defaults.RESERVED_KEYS`` lists.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#two-keys-written-as-one-are-refused
    """
    written: dict[Any, Any] = {}
    spelled_by: dict[Any, Any] = {}
    for k, v in instance.items():
        key = _serialize_leaf(kt, k, opts.native_types)
        if checked:
            _warn_an_unread_key(kt, k, key, path, opts)
        if key in spelled_by:
            where = _spell_field_path(path)
            raise ConfargError.keys_serialized_alike(spelled_by[key], k, key, where)
        spelled_by[key] = k
        written[_data_key(key, (*path, str(k)))] = item(v, str(k))
    return written


def _warn_an_unread_key(kt: Any, key: Any, written: Any, path: FieldPath, opts: _DumpOptions) -> None:
    """Warn that the key *key* of a dict keyed by *kt*, at *path*, will not read back as itself.

    A key is read back from the text a file writes it as (:func:`_key_spelling`), as a token;
    it reads back when *kt* holds it and reads that text as an equal value. No ``__cast__``
    spells a key, so the dump writes it and warns, as it does a value no cast can pin
    (:func:`_warn_unpinnable_leaf`).

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-key-that-does-not-read-back-is-written-with-a-warning
    """
    text = written if isinstance(written, str) else _key_spelling(written)
    reading = _what_reading_answers(
        lambda: read_key(kt, text, path),
        key,
        written,
        lambda back: _serialize_leaf(kt, back, opts.native_types),
        it="its text",
        held=_holds(_resolve_type(kt), key),
    )
    if reading is None:
        return
    warnings.warn(
        f"Key {text!r} at {_spelled_where(path)} will not read back as"
        f" {_spell_type(type(key))}: {_spell_type(kt)} {reading}.",
        ConfargWarning,
        stacklevel=2,
    )


def _is_nan(value: Any) -> bool:
    """Return whether *value* is a float NaN, which compares equal to nothing it reads back as."""
    return isinstance(value, float) and math.isnan(value)


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


def _serialize_leaf(tp: Any, value: Any, native_types: tuple[type, ...] = ()) -> Any:
    """Serialize a leaf value: Enum → .value, registered leaf → its serializer, else passthrough.

    A registered leaf whose type *native_types* names is kept as the object it is.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    if isinstance(value, _StrToken):
        return str(value)
    if (form := _object_form(value, native_types)) is not value:
        return form
    if tp is float and isinstance(value, int) and not isinstance(value, bool):
        with contextlib.suppress(OverflowError):  # no float holds it: the dump records the int
            return float(value)
    if (builtin := _subclassed_scalar(value)) is not None:
        return builtin(value)  # the builtin a writer holds, which reads back as the subclass
    if isinstance(value, type):
        return _class_path(value)
    return value


def _subclassed_scalar(value: Any) -> type | None:
    """Return str, int or float when *value* is an instance of a subclass of one, None otherwise.

    Asked of the value, not the declared type, so a subclass instance in a ``str`` or an ``Any``
    field leaves as the builtin too: PyYAML's writer refuses a subclass it has no representer
    for. A bool is no subclass here, and an Enum member and a token are written before.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-builtins-subclass-is-that-builtin.md#a-subclass-is-built-by-its-constructor
    """
    if type(value) is bool:
        return None
    return next((b for b in (str, int, float) if isinstance(value, b) and type(value) is not b), None)


def _object_form(value: Any, native_types: tuple[type, ...] = ()) -> Any:
    """Return the form a file holds an object in: an Enum member's value, a registered leaf's serialized form.

    A registered leaf is written by the serializer of its most specific registered type
    (:func:`_registered_leaf_of`), so a ``datetime`` by its own, not ``date``'s, and kept as
    it is when *native_types* names that type. Any other value is returned as it is, a token
    included: a token is a str subclass, and registering ``str`` must not let one leak out.
    isinstance, so a token subclass (_UnionSeqToken) is caught too; it still spares a
    caller's own str subclass, which cannot inherit from a private type. See
    docs-dev/architecture/invariants.md#tokens-mean-untyped-text.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-writer-may-hold-a-date-natively
    """
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, _StrToken):
        return value
    leaf_tp = _registered_leaf_of(value)
    if leaf_tp is None or (leaf_tp in native_types and _a_writer_holds(value)):
        return value
    return _LEAF_SERIALIZERS[leaf_tp](value)


def _a_writer_holds(value: Any) -> bool:
    """Return whether a writer holding *value*'s type reads *value* back: no offset with seconds.

    PyYAML and ``tomli_w`` write a datetime whose UTC offset is no whole number of minutes
    (``+00:09:21``, Paris' mean time) as text neither reads back, so such a value is
    written as its ISO text, which does.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-writer-may-hold-a-date-natively
    """
    offset = value.utcoffset() if isinstance(value, datetime | time) else None
    return offset is None or offset % timedelta(minutes=1) == timedelta(0)


def written_form(value: Any) -> Any:
    """Return *value* as an expression writes it into text: each Enum member and registered leaf in its dump form.

    What an interpolation stringifies and a computed key spells: the form :func:`_serialize_leaf`
    dumps such an object in, never its ``str()``, so ``${c}`` writes ``red`` and a path its
    forward slashes. A dict or a list is walked, and copied only where something in it changed;
    anything else is returned as it is.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
    """
    return _walk_written(value, (), lambda leaf, _: _object_form(leaf))


def left_form(value: Any, path: tuple[Hashable, ...]) -> Any:
    """Return *value* as a whole expression at *path* leaves it in the data.

    As :func:`written_form` writes it, but for an unregistered subclass of a registered leaf,
    left as its class tag: its parent's form would rebuild the parent. One no tag reads back
    keeps that form, with a :class:`ConfargWarning` naming *path*.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-whole-expression-leaves-a-subclass-as-its-tag
    """

    def leaf_form(leaf: Any, at: FieldPath) -> Any:
        if _is_a_registered_leafs_subclass(leaf):
            return _serialize_read_leaf(_registered_leaf_of(leaf), leaf, at, _DumpOptions("auto"))
        return _object_form(leaf)

    return _walk_written(value, tuple(s if isinstance(s, str | int) else str(s) for s in path), leaf_form)


def _walk_written(value: Any, path: FieldPath, leaf_form: Callable[[Any, FieldPath], Any]) -> Any:
    """Return *value* with *leaf_form* applied to what it holds, copying only where something changed."""
    if isinstance(value, dict):
        items = {k: _walk_written(v, (*path, str(k)), leaf_form) for k, v in value.items()}
        return value if all(items[k] is v for k, v in value.items()) else items
    if isinstance(value, list):
        elements = [_walk_written(v, (*path, i), leaf_form) for i, v in enumerate(value)]
        return value if all(a is b for a, b in zip(elements, value, strict=True)) else elements
    return leaf_form(value, path)


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


def _serialize_untyped(value: Any, native_types: tuple[type, ...] = ()) -> Any:
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
    A registered leaf whose type *native_types* names is kept as the object it is.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    if isinstance(value, _Pinned):
        return _serialize_pinned(value, native_types)
    if isinstance(value, _DeleteSentinel):
        return {_defaults.UNSET_KEY: True}
    if isinstance(value, dict) and isinstance(value.get(ListOp.BASE), _DeleteSentinel):
        rest = {k: v for k, v in value.items() if k is not ListOp.BASE}
        return {_defaults.UNSET_KEY: True, **_serialize_untyped(rest, native_types)}
    if isinstance(value, dict):
        return {(str(k) if isinstance(k, ListOp) else k): _serialize_untyped(v, native_types) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_untyped(v, native_types) for v in value]
    return _serialize_leaf(None, value, native_types)


def _serialize_pinned(pin: _Pinned, native_types: tuple[type, ...] = ()) -> dict[str, Any]:
    """Write a force-cast as the ``{__cast__, __value__}`` dict ``_try_pinned_dict`` reads back.

    The pinned value goes back through :func:`_serialize_untyped`, which unwraps the
    ``_StrToken`` a CLI cast pins and walks a container a file cast may hold.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#cast-pinning-in-files
    """
    return _cast_dict(pin.tp, _serialize_untyped(pin.value, native_types))


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


def _needs_tag(tp: Any, variant_tp: Any, serialized_data: dict[str, Any]) -> bool:
    """Check if a class tag is needed: whether disambiguating the serialized data selects anything but *variant_tp*.

    A single match that is another variant reads the data back as that variant, and a variant
    that demands its tag matches nothing without it.
    """
    struct_vars = [v for v in _union_args_no_none(tp) if _is_struct_variant(_resolve_type(v))]
    # A dump's keys are names, which a merged dict's keys include: the match only reads them.
    return _disambiguate_struct(struct_vars, cast("MergeDict", serialized_data)) != [variant_tp]


def _sort_key(value: Any) -> tuple[str, str]:
    """Sort key for heterogeneous set/frozenset serialization."""
    return (type(value).__name__, str(value))

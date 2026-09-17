# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Serialization of dataclass instances to plain dicts (the inverse of construction).

Dev Notes:
    docs-dev/architecture/05-types-and-construction.md#serialization
"""

from __future__ import annotations

import enum
import warnings
from typing import Any

from confarg import _defaults
from confarg._callable import _serialize_callable
from confarg._cast import cast_name_for_type
from confarg._types import (
    TagPolicy,
    _dict_kv,
    _elem_type,
    _fixed_seq_types,
    _is_callable,
    _is_dict,
    _is_frozenset,
    _is_list,
    _is_literal,
    _is_namedtuple,
    _is_set,
    _is_struct,
    _is_tuple,
    _is_union,
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
from confarg.exceptions import ConfargError, ConfargWarning
from confarg.typedload._coerce import _LEAF_SERIALIZERS, _is_struct_variant
from confarg.typedload._construct import _disambiguate_struct, construct


def _serialize(
    tp: Any,
    instance: Any,
    path: str,
    union_tag: str,
    tag_policy: TagPolicy,
) -> Any:
    """Serialize a typed value to a plain dict/list/leaf structure.

    Args:
        tp: The declared type of the value.
        instance: The value to serialize.
        path: Dot-separated field path for diagnostics.
        union_tag: The field name used as a discriminator tag in unions.
        tag_policy: "auto" or "always".

    Returns:
        A JSON-compatible structure (dict, list, or leaf value).
    """
    tp = _resolve_type(tp)
    if instance is None:
        return None
    if _is_callable(tp):
        return _serialize_callable(instance)
    return _serialize_by_type(tp, instance, path, union_tag, tag_policy)


def _serialize_by_type(  # noqa: PLR0911
    tp: Any,
    instance: Any,
    path: str,
    union_tag: str,
    tag_policy: TagPolicy,
) -> Any:
    """Dispatch serialization by type after None and callable are handled."""
    if _is_union(tp):
        return _serialize_union(tp, instance, path, union_tag, tag_policy)
    if _is_namedtuple(tp):
        return _serialize_namedtuple(tp, instance, path, union_tag, tag_policy)
    if _is_struct_variant(tp):
        return _serialize_struct(tp, instance, path, union_tag, tag_policy)
    if _is_list(tp) or _is_set(tp) or _is_frozenset(tp):
        return _serialize_collection(tp, instance, path, union_tag, tag_policy)
    if _is_tuple(tp):
        return _serialize_tuple(tp, instance, path, union_tag, tag_policy)
    if _is_dict(tp):
        return _serialize_dict(tp, instance, path, union_tag, tag_policy)
    return _serialize_leaf(tp, instance)


def _serialize_collection(
    tp: Any,
    instance: Any,
    path: str,
    union_tag: str,
    tag_policy: TagPolicy,
) -> list[Any]:
    """Serialize a list, set, or frozenset."""
    et = _elem_type(tp)
    if _is_list(tp):
        return [_serialize(et, v, f"{path}[{i}]", union_tag, tag_policy) for i, v in enumerate(instance)]
    items = [_serialize(et, v, path, union_tag, tag_policy) for v in instance]
    return sorted(items, key=_sort_key)


def _serialize_namedtuple(
    tp: Any,
    instance: Any,
    path: str,
    union_tag: str,
    tag_policy: TagPolicy,
) -> dict[str, Any]:
    """Serialize a namedtuple instance to a dict keyed by field name."""
    flds = _namedtuple_fields(tp)
    out: dict[str, Any] = {}
    for name, ft in flds.items():
        value = getattr(instance, name)
        fp = f"{path}.{name}" if path else name
        out[name] = _serialize(ft, value, fp, union_tag, tag_policy)
    return out


def _serialize_struct(
    tp: Any,
    instance: Any,
    path: str,
    union_tag: str,
    tag_policy: TagPolicy,
) -> dict[str, Any]:
    """Serialize a dataclass or plain-class instance to a dict."""
    actual_tp = type(instance)
    if actual_tp is not tp and _is_struct(actual_tp) and issubclass(actual_tp, tp):
        out = _serialize_struct(actual_tp, instance, path, union_tag, tag_policy)
        out[union_tag] = f"{actual_tp.__module__}.{actual_tp.__name__}"
        return out
    flds = _struct_fields(tp)
    out: dict[str, Any] = {}
    for name, ft in flds.items():
        try:
            value = getattr(instance, name)
        except AttributeError:
            msg = (
                f"Field '{name}' is declared in {type(instance).__name__}.__init__"
                f" but not accessible on the instance as self.{name}."
                f" Plain classes must store every __init__ parameter as a same-named instance attribute."
            )
            raise ConfargError(msg) from None
        fp = f"{path}.{name}" if path else name
        out[name] = _serialize(ft, value, fp, union_tag, tag_policy)
    return out


def _serialize_union(
    tp: Any,
    instance: Any,
    path: str,
    union_tag: str,
    tag_policy: TagPolicy,
) -> Any:
    """Serialize a Union value, adding a class tag or a force-cast when needed.

    A struct variant is disambiguated by the class tag; a leaf variant whose bare form another
    variant would steal back is written as its ``{__cast__, __value__}`` spelling instead, and
    warns when no cast can name it.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#casting-a-stolen-leaf
    """
    variant_tp = _find_variant_type(tp, instance)
    if variant_tp is None:
        return instance

    serialized = _serialize(variant_tp, instance, path, union_tag, tag_policy)

    if _is_struct_variant(variant_tp):
        if isinstance(serialized, dict) and (tag_policy == "always" or _needs_tag(tp, serialized, union_tag)):
            serialized[union_tag] = f"{variant_tp.__module__}.{variant_tp.__name__}"
        return serialized

    if _reads_back(tp, instance, serialized, union_tag):
        return serialized
    cast = _cast_dict(variant_tp, serialized)
    if _reads_back(tp, instance, cast, union_tag):
        return cast
    _warn_unpinnable_leaf(variant_tp, serialized, path)
    return serialized


def _warn_unpinnable_leaf(variant_tp: Any, serialized: Any, path: str) -> None:
    """Warn that a leaf no ``__cast__`` can name will read back as another union variant.

    Args:
        variant_tp: The variant the value was serialized as.
        serialized: Its bare serialized form, written as-is.
        path: Dot-separated field path for diagnostics.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#casting-a-stolen-leaf
    """
    warnings.warn(
        f"Value at '{path or _defaults.ROOT_KEY}' will not read back as"
        f" {getattr(variant_tp, '__name__', variant_tp)!r}: another union variant takes the"
        f" dumped {type(serialized).__name__}, and no __cast__ names that type."
        f" confarg.register_leaf_type makes it nameable.",
        ConfargWarning,
        stacklevel=2,
    )


def _reads_back(tp: Any, instance: Any, data: Any, union_tag: str) -> bool:
    """Check that reading *data* back as *tp* produces *instance* again.

    Runs the reader itself instead of modelling a second time what selects a variant, so the
    answer follows whatever decides it — the stealing rule, declaration order or a tag.

    Args:
        tp: The declared type the value would be read back as.
        instance: The value that produced *data*.
        data: The serialized form to read back.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        True if construction yields a value of the same type that compares equal.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#casting-a-stolen-leaf
    """
    try:
        back = construct(tp, data, union_tag=union_tag)
        # `is` first: a value that passes through unchanged round-trips even when it does not
        # compare equal to itself (float('nan')).
        return type(back) is type(instance) and bool(back is instance or back == instance)
    except (ConfargError, TypeError, ValueError):
        return False


def _serialize_tuple(
    tp: Any,
    instance: Any,
    path: str,
    union_tag: str,
    tag_policy: TagPolicy,
) -> list[Any]:
    """Serialize a tuple to a list."""
    tt = _tuple_types(tp)
    if tt is None:
        et = _elem_type(tp)
        return [_serialize(et, v, f"{path}[{i}]", union_tag, tag_policy) for i, v in enumerate(instance)]
    return [
        _serialize(et, v, f"{path}[{i}]", union_tag, tag_policy)
        for i, (et, v) in enumerate(zip(tt, instance, strict=False))
    ]


def _serialize_dict(
    tp: Any,
    instance: Any,
    path: str,
    union_tag: str,
    tag_policy: TagPolicy,
) -> dict[Any, Any]:
    """Serialize a typed dict."""
    kt, vt = _dict_kv(tp)
    return {
        _serialize_leaf(kt, k): _serialize(vt, v, f"{path}.{k}", union_tag, tag_policy) for k, v in instance.items()
    }


def _serialize_leaf(tp: Any, value: Any) -> Any:
    """Serialize a leaf value: Enum → .value, registered leaf → its serializer, else passthrough.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#serialization
    """
    if isinstance(value, enum.Enum):
        return value.value
    # Before the registry loop: a token is a str subclass, and registering ``str`` must not
    # let one leak out. isinstance, so a token subclass (_UnionSeqToken) is caught too; it
    # still spares a caller's own str subclass, which cannot inherit from a private type.
    # See docs-dev/architecture/09-invariants.md#tokens-mean-untyped-text.
    if isinstance(value, _StrToken):
        return str(value)
    for leaf_tp, serialize in _LEAF_SERIALIZERS.items():
        # isinstance, not an exact type test: a real Path is a WindowsPath or a PosixPath.
        if isinstance(value, leaf_tp):
            return serialize(value)
    if tp is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    return value


def _serialize_untyped(value: Any) -> Any:
    """Serialize a raw merged dict: containers recursed, leaves through _serialize_leaf.

    The counterpart of :func:`_serialize` for data that carries no declared types
    (the dict accepted by ``dump_file``), so only the type-less leaf rules apply:
    ``Enum`` becomes its value, ``Path`` a string, ``_StrToken`` a plain ``str``.
    An ``int`` is never widened to ``float`` — nothing here says it should be one.

    A force-cast is written back as the ``{__cast__, __value__}`` dict a file spells it
    with, rather than as the value it pins: nothing here knows the declared type, and a
    bare scalar is re-read by declaration order.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#serialization
    """
    if isinstance(value, _Pinned):
        return _serialize_pinned(value)
    if isinstance(value, dict):
        return {k: _serialize_untyped(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_untyped(v) for v in value]
    return _serialize_leaf(None, value)


def _serialize_pinned(pin: _Pinned) -> dict[str, Any]:
    """Write a force-cast as the ``{__cast__, __value__}`` dict ``_try_pinned_dict`` reads back.

    The pinned value goes back through :func:`_serialize_untyped`, which unwraps the
    ``_StrToken`` a CLI cast pins and walks a container a file cast may hold.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#cast-pinning-in-files
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
        docs-dev/architecture/05-types-and-construction.md#cast-pinning-in-files
    """
    return {"__cast__": cast_name_for_type(tp), "__value__": value}


def _find_variant_type(tp: Any, instance: Any) -> Any | None:
    """Find which Union variant the instance belongs to, in declaration order."""
    args = _union_args_no_none(tp)
    for arg in args:
        arg_r = _resolve_type(arg)
        if _variant_holds(arg_r, instance):
            return arg_r
    return None


def _variant_holds(tp: Any, instance: Any) -> bool:  # noqa: PLR0911  # one branch per shape, as in the dispatcher
    """True if *instance* is a value of union variant *tp*.

    Asks the shape functions in the order :func:`_serialize_by_type` dispatches in, so the
    variant chosen here is the one that then serializes the value. A bare ``isinstance``
    cannot ask: a parameterized generic and a ``Literal`` both refuse to be its second
    argument, which left every union holding one undumpable. Each shape answers with the
    concrete class construction builds for it -- ``list`` for ``Sequence[X]``, ``dict`` for
    ``Mapping[K, V]`` -- and a ``Literal`` answers by membership, so ``True`` is not a value
    of ``Literal[1]``.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#serialization
    """
    if _is_namedtuple(tp) or _is_struct_variant(tp):
        return isinstance(instance, tp)
    if _is_list(tp):
        return isinstance(instance, list)
    if _is_set(tp):
        return isinstance(instance, set)
    if _is_frozenset(tp):
        return isinstance(instance, frozenset)
    if _is_tuple(tp):
        fixed = _fixed_seq_types(tp)
        return isinstance(instance, tuple) and (fixed is None or len(instance) == len(fixed))
    if _is_dict(tp):
        return isinstance(instance, dict)
    if _is_literal(tp):
        return any(type(m) is type(instance) and m == instance for m in _literal_values(tp))
    # What is left is a class, or is parameterized over one (``type[X]``, ``Callable[..., X]``);
    # ``Any`` is neither, and holds nothing in particular.
    origin = _origin(tp)
    checkable = origin if isinstance(origin, type) else tp
    return isinstance(checkable, type) and isinstance(instance, checkable)


def _needs_tag(tp: Any, serialized_data: dict[str, Any], union_tag: str) -> bool:
    """Check if a class tag is needed by running disambiguation on the serialized data."""
    struct_vars = [v for v in _union_args_no_none(tp) if _is_struct_variant(_resolve_type(v))]
    if len(struct_vars) <= 1:
        return False
    matches = _disambiguate_struct(struct_vars, serialized_data, union_tag)
    return len(matches) != 1


def _sort_key(value: Any) -> tuple[str, str]:
    """Sort key for heterogeneous set/frozenset serialization."""
    return (type(value).__name__, str(value))

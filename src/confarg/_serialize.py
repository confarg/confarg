# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Serialization of dataclass instances to plain dicts."""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any

from confarg._callable import _serialize_callable
from confarg._types import (
    TagPolicy,
    _dict_kv,
    _elem_type,
    _is_callable,
    _is_dict,
    _is_frozenset,
    _is_list,
    _is_namedtuple,
    _is_set,
    _is_struct,
    _is_tuple,
    _is_union,
    _namedtuple_fields,
    _resolve_type,
    _StrToken,
    _struct_fields,
    _tuple_types,
    _union_args_no_none,
)
from confarg.exceptions import ConfargError
from confarg.typedload._construct import _disambiguate_struct


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
    if _is_struct(tp):
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
    """Serialize a Union value, adding a class tag when needed."""
    variant_tp = _find_variant_type(tp, instance)
    if variant_tp is None:
        return instance

    serialized = _serialize(variant_tp, instance, path, union_tag, tag_policy)

    if (
        _is_struct(variant_tp)
        and isinstance(serialized, dict)
        and (tag_policy == "always" or _needs_tag(tp, serialized, union_tag))
    ):
        serialized[union_tag] = f"{variant_tp.__module__}.{variant_tp.__name__}"

    return serialized


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
    """Serialize a leaf value: Enum → .value, Path → str, float → float, else passthrough."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if tp is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if type(value) is _StrToken:
        return str(value)
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    return value


def _find_variant_type(tp: Any, instance: Any) -> Any | None:
    """Find which Union variant matches the instance's type."""
    args = _union_args_no_none(tp)
    for arg in args:
        arg_r = _resolve_type(arg)
        if isinstance(instance, arg_r):
            return arg_r
    return None


def _needs_tag(tp: Any, serialized_data: dict[str, Any], union_tag: str) -> bool:
    """Check if a class tag is needed by running disambiguation on the serialized data."""
    struct_vars = [v for v in _union_args_no_none(tp) if _is_struct(_resolve_type(v))]
    if len(struct_vars) <= 1:
        return False
    matches = _disambiguate_struct(struct_vars, serialized_data, union_tag)
    return len(matches) != 1


def _sort_key(value: Any) -> tuple[str, str]:
    """Sort key for heterogeneous set/frozenset serialization."""
    return (type(value).__name__, str(value))

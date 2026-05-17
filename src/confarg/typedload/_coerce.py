# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Leaf value coercion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from confarg._import import _import_dotted
from confarg._types import (
    _final_inner,
    _is_enum,
    _is_final,
    _is_literal,
    _is_none_type,
    _is_union,
    _literal_values,
    _resolve_type,
    _StrToken,
    _type_ref_constraint,
    _union_args_no_none,
)
from confarg.exceptions import SymbolImportError, TypeCoercionError

_TRUTHY = frozenset({"true", "1", "yes", "on"})
_FALSY = frozenset({"false", "0", "no", "off"})
_NONE_TOKENS = frozenset({"none", "null"})
_LEAF_COERCIONS: dict[type, Any] = {Path: Path}


def _src_type(value: Any) -> str:
    """Return the user-visible type name of a value, collapsing _StrToken to 'str'."""
    return "str" if isinstance(value, _StrToken) else type(value).__name__


def _coerce_bool(s: str) -> bool:
    """Coerce a string to a boolean value.

    Args:
        s: The string to coerce (e.g. "true", "1", "yes", "on").

    Returns:
        The corresponding boolean value.

    Raises:
        TypeCoercionError: If the string is not a recognized boolean representation.
    """
    low = s.lower()
    if low in _TRUTHY:
        return True
    if low in _FALSY:
        return False
    valid = sorted(_TRUTHY | _FALSY)
    msg = f"Cannot coerce {s!r} to bool. Valid values: {valid}"
    raise TypeCoercionError(msg)


def _coerce_type_ref(tp: Any, value: Any, path: str = "") -> type:
    """Coerce a dotted-path string or class object to a class, validated against type[X]."""
    if isinstance(value, type):
        constraint = _type_ref_constraint(tp)
        if constraint is not object and not issubclass(value, constraint):
            msg = (
                f"Class {value.__module__}.{value.__qualname__!r} at '{path}'"
                f" is not a subclass of {constraint.__module__}.{constraint.__name__}."
            )
            raise TypeCoercionError(msg)
        return value
    if not isinstance(value, _StrToken):
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "type", path)
    try:
        obj = _import_dotted(str(value))
    except SymbolImportError as e:
        msg = (
            f"Cannot import class {str(value)!r} at '{path}': {e}."
            f" Use a fully-qualified dotted path, e.g. 'mypackage.MyClass'."
        )
        raise TypeCoercionError(msg) from e
    if not isinstance(obj, type):
        msg = f"Cannot coerce {str(value)!r} at '{path}': expected a class, got {type(obj).__name__!r}."
        raise TypeCoercionError(msg)
    constraint = _type_ref_constraint(tp)
    if constraint is not object and not issubclass(obj, constraint):
        msg = f"Class {str(value)!r} at '{path}' is not a subclass of {constraint.__module__}.{constraint.__name__}."
        raise TypeCoercionError(msg)
    return obj


def _coerce_bool_value(value: Any, path: str) -> bool:
    """Coerce a raw value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, _StrToken):
        return _coerce_bool(str(value))
    raise TypeCoercionError.cannot_coerce(_src_type(value), value, "bool", path)


def _coerce_int_value(value: Any, path: str) -> int:
    """Coerce a raw value to int."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, _StrToken):
        try:
            return int(str(value), 0)
        except (ValueError, TypeError):
            raise TypeCoercionError.cannot_coerce(_src_type(value), value, "int", path) from None
    raise TypeCoercionError.cannot_coerce(_src_type(value), value, "int", path)


def _coerce_float_value(value: Any, path: str) -> float:
    """Coerce a raw value to float."""
    if isinstance(value, float) and not isinstance(value, bool):
        return value
    if isinstance(value, _StrToken):
        try:
            return float(str(value))
        except (ValueError, TypeError):
            raise TypeCoercionError.cannot_coerce(_src_type(value), value, "float", path) from None
    raise TypeCoercionError.cannot_coerce(_src_type(value), value, "float", path)


def _coerce_str_value(value: Any, path: str) -> str:
    """Coerce a raw value to str."""
    if isinstance(value, str):  # _StrToken is a str subclass
        return str(value)
    raise TypeCoercionError.cannot_coerce(_src_type(value), value, "str", path)


def _match_literal_str_token(vals: tuple[Any, ...], value: _StrToken, path: str) -> Any:
    """Try to match a _StrToken against Literal members; return the matched member or raise."""
    s = str(value)

    if s.lower() in _NONE_TOKENS:
        for v in vals:
            if v is None:
                return v

    # Enum members and bytes: exact string-representation match
    for v in vals:
        if v is not None and _is_enum(type(v)) and str(v) == s:
            return v
        if isinstance(v, bytes) and str(v) == s:
            return v

    # Scalar types: stealing rule — try non-str before str
    scalar_non_str = [v for v in vals if v is not None and not isinstance(v, (str, bytes)) and not _is_enum(type(v))]
    str_members = [v for v in vals if isinstance(v, str)]
    for v in scalar_non_str + str_members:
        try:
            if _coerce_leaf(type(v), value, path) == v:
                return v
        except (TypeCoercionError, ValueError, TypeError):
            continue

    raise TypeCoercionError.cannot_coerce(_src_type(value), value, f"Literal{vals}", path)


def _coerce_literal_value(tp: Any, value: Any, path: str) -> Any:
    """Coerce a raw value to a Literal type."""
    vals = _literal_values(tp)
    if not isinstance(value, _StrToken):
        for v in vals:
            if type(v) is type(value) and v == value:
                return v
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, f"Literal{vals}", path)
    return _match_literal_str_token(vals, value, path)


def _coerce_enum_value(tp: Any, value: Any, path: str) -> Any:
    """Coerce a raw value to an Enum member."""
    if isinstance(value, tp):
        return value
    s = str(value)
    try:
        return tp[s]
    except KeyError:
        for member in tp:
            if str(member.value) == s:
                return member
        members = []
        for m in tp:
            sv = str(m.value)
            members.append(f"'{m.name}' ('{sv}')" if sv != m.name else f"'{m.name}'")
        msg = (
            f"Cannot coerce {_src_type(value)} {value!r} to {tp.__name__} at '{path}'."
            f" Valid members: {', '.join(members)}"
        )
        raise TypeCoercionError(msg) from None


def _enum_choices(tp: Any) -> list[str]:
    """Return accepted string representations for an enum type: names first, then distinct values."""
    return list(dict.fromkeys([e.name for e in tp] + [str(e.value) for e in tp]))


def _is_registered_leaf(tp: Any) -> bool:
    """True if tp was registered via register_leaf_type and should be treated as a leaf."""
    return tp in _LEAF_COERCIONS


_SCALAR_COERCIONS: dict[type, Any] = {
    bool: _coerce_bool_value,
    int: _coerce_int_value,
    float: _coerce_float_value,
    str: _coerce_str_value,
}


def _coerce_registered(tp: Any, value: Any, path: str) -> Any:
    """Coerce value to a type registered in _LEAF_COERCIONS, passing instances through."""
    if isinstance(value, tp):
        return value
    try:
        return _LEAF_COERCIONS[tp](value)
    except (TypeError, ValueError, OSError):
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, tp.__name__, path) from None


def _coerce_leaf(tp: Any, value: Any, path: str = "") -> Any:  # noqa: PLR0911  # one branch per leaf type
    """Coerce a raw value to the target leaf type.

    Handles bool, int, float, str, Literal, Enum, Path, and NoneType.

    Args:
        tp: The target type to coerce to.
        value: The raw value to coerce.
        path: Dot-separated field path for error messages.

    Returns:
        The coerced value matching the target type.

    Raises:
        TypeCoercionError: If the value cannot be coerced to the target type.
    """
    tp = _resolve_type(tp)
    if _is_none_type(tp):
        if value is None:
            return None
        if isinstance(value, _StrToken) and (str(value).lower() in _NONE_TOKENS or str(value) == ""):
            return None
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "None", path)
    if _is_final(tp):
        return _coerce_leaf(_final_inner(tp), value, path)
    if tp in _SCALAR_COERCIONS:
        return _SCALAR_COERCIONS[tp](value, path)
    if _is_literal(tp):
        return _coerce_literal_value(tp, value, path)
    if _is_enum(tp):
        return _coerce_enum_value(tp, value, path)
    if tp in _LEAF_COERCIONS:
        return _coerce_registered(tp, value, path)
    msg = f"Unsupported leaf type {tp} at '{path}'"
    raise TypeCoercionError(msg)


def _try_coerce(ft: Any, token: _StrToken) -> Any:
    """Coerce a string token to the target type if unambiguous.

    Coerces immediately for concrete leaf types (bool, int, float, registered
    types in _LEAF_COERCIONS, Literal, Enum) so the merged dict has consistent
    types regardless of source.  str tokens are returned unchanged — _StrToken
    is already a str subclass.  For multi-variant unions, returns token
    unchanged for construct() to handle.
    """
    if ft is None:
        return token
    ft = _resolve_type(ft)
    if _is_union(ft):
        non_none = _union_args_no_none(ft)
        if len(non_none) != 1:
            return token
        ft = _resolve_type(non_none[0])
    if not (_is_literal(ft) or _is_enum(ft) or ft in (bool, int, float) or ft in _LEAF_COERCIONS or _is_none_type(ft)):
        return token
    try:
        return _coerce_leaf(ft, token)
    except TypeCoercionError:
        return token

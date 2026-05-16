# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Leaf value coercion for confarg."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from confarg._errors import TypeCoercionError
from confarg._types import (
    _is_enum,
    _is_literal,
    _is_none_type,
    _literal_values,
    _resolve_type,
    _StrToken,
)

_TRUTHY = frozenset({"true", "1", "yes", "on"})
_FALSY = frozenset({"false", "0", "no", "off"})
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
    raise TypeCoercionError(f"Cannot coerce {s!r} to bool. Valid values: {valid}")


def _coerce_type_ref(tp: Any, value: Any, path: str = "") -> type:
    """Coerce a dotted-path string or class object to a class, validated against type[X]."""
    from confarg._callable import _import_dotted
    from confarg._types import _type_ref_constraint

    if isinstance(value, type):
        constraint = _type_ref_constraint(tp)
        if constraint is not object and not issubclass(value, constraint):
            raise TypeCoercionError(
                f"Class {value.__module__}.{value.__qualname__!r} at '{path}'"
                f" is not a subclass of {constraint.__module__}.{constraint.__name__}."
            )
        return value
    if not isinstance(value, _StrToken):
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "type", path)
    try:
        obj = _import_dotted(str(value))
    except TypeCoercionError as e:
        raise TypeCoercionError(
            f"Cannot import class {str(value)!r} at '{path}': {e}."
            f" Use a fully-qualified dotted path, e.g. 'mypackage.MyClass'."
        ) from e
    if not isinstance(obj, type):
        raise TypeCoercionError(
            f"Cannot coerce {str(value)!r} at '{path}': expected a class, got {type(obj).__name__!r}."
        )
    constraint = _type_ref_constraint(tp)
    if constraint is not object and not issubclass(obj, constraint):
        raise TypeCoercionError(
            f"Class {str(value)!r} at '{path}' is not a subclass of {constraint.__module__}.{constraint.__name__}."
        )
    return obj


def _coerce_leaf(tp: Any, value: Any, path: str = "") -> Any:
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
        return None

    if tp is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, _StrToken):
            return _coerce_bool(str(value))
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "bool", path)

    if tp is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, _StrToken):
            try:
                return int(str(value))
            except (ValueError, TypeError):
                raise TypeCoercionError.cannot_coerce(_src_type(value), value, "int", path) from None
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "int", path)

    if tp is float:
        if isinstance(value, float) and not isinstance(value, bool):
            return value
        if isinstance(value, _StrToken):
            try:
                return float(str(value))
            except (ValueError, TypeError):
                raise TypeCoercionError.cannot_coerce(_src_type(value), value, "float", path) from None
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "float", path)

    if tp is str:
        if isinstance(value, str):  # _StrToken is a str subclass
            return str(value)
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "str", path)

    if _is_literal(tp):
        vals = _literal_values(tp)
        if isinstance(value, _StrToken):
            s = str(value)
            for v in vals:
                if str(v) == s:
                    return v
        else:
            for v in vals:
                if type(v) is type(value) and v == value:
                    return v
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, f"Literal{vals}", path)

    if _is_enum(tp):
        if isinstance(value, tp):
            return value
        s = str(value)
        for member in tp:
            if str(member.value) == s:
                return member
        try:
            return tp[s]
        except KeyError:
            members = []
            for m in tp:
                sv = str(m.value)
                members.append(f"'{m.name}' ('{sv}')" if sv != m.name else f"'{m.name}'")
            raise TypeCoercionError(
                f"Cannot coerce {_src_type(value)} {value!r} to {tp.__name__} at '{path}'."
                f" Valid members: {', '.join(members)}"
            ) from None

    if tp in _LEAF_COERCIONS:
        try:
            return _LEAF_COERCIONS[tp](value)
        except Exception:
            raise TypeCoercionError.cannot_coerce(_src_type(value), value, tp.__name__, path) from None

    raise TypeCoercionError(f"Unsupported leaf type {tp} at '{path}'")

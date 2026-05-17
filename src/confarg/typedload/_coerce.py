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
    _is_struct,
    _is_union,
    _literal_values,
    _resolve_type,
    _StrToken,
    _type_ref_constraint,
    _union_args_no_none,
)
from confarg.dictexpr import contains_expression
from confarg.exceptions import SymbolImportError, TypeCoercionError

_TRUTHY = frozenset({"true", "1", "yes", "on"})
_FALSY = frozenset({"false", "0", "no", "off"})
_NONE_TOKENS = frozenset({"none", "null"})
_LEAF_COERCIONS: dict[type, Any] = {Path: Path}
_LEAF_SERIALIZERS: dict[type, Any] = {Path: str}


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


_RANKED_LEAF_TYPES: tuple[type, ...] = (float, int, bool, type(None), str)


def _steal_rank(tp: Any) -> int:
    """Return the stealing priority of a leaf type — lower steals first.

    A registered leaf ranks first, then ``Enum``, then every kind the rule does not name
    (type references, ``Literal``, a ``bytes`` Literal member), then float, int, bool, None
    and str. Types sharing a rank keep their declaration order, ``_steal_order`` being stable.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#stealing-rule
    """
    if _is_registered_leaf(tp):
        return 0
    if _is_enum(tp):
        return 1
    for i, ranked in enumerate(_RANKED_LEAF_TYPES):
        if tp is ranked:  # identity: bool is a subclass of int and ranks on its own
            return 3 + i
    return 2


def _steal_order(variants: list[Any], *, key: Any) -> list[Any]:
    """Sort variants into stealing priority, declaration order breaking ties.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#stealing-rule

    Args:
        variants: The list to order.
        key: Callable returning the type to classify each variant by.
    """
    return sorted(variants, key=lambda v: _steal_rank(_resolve_type(key(v))))


def _match_literal_member(v: Any, value: Any, path: str) -> bool:  # noqa: PLR0911  # one branch per member kind
    """Return True if value matches Literal member v.

    One rule for both channels: a ``_StrToken`` from the CLI and a native value
    from a config file. For an ``Enum`` member, the value may be the member
    itself, its name, or its value — the last is what ``dump()`` writes, so a
    ``Literal`` over ``Enum`` round-trips. The repr match (``"Color.RED"``)
    is a CLI affordance: a plain file string is never re-read as a repr.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#stealing-rule
    """
    tp_v = type(v)
    if _is_enum(tp_v):
        if type(value) is tp_v:
            return value == v
        if isinstance(value, _StrToken) and str(v) == str(value):
            return True  # repr match: "Color.RED" == "Color.RED" (CLI only)
        try:  # name/value match: "RED" or "red" → Color.RED
            return _coerce_leaf(tp_v, value, path) == v
        except (TypeCoercionError, ValueError, TypeError):
            return False
    if isinstance(v, bytes):
        if isinstance(value, _StrToken):
            return str(v) == str(value)
        return type(value) is tp_v and value == v
    if type(value) is tp_v:
        return value == v
    if isinstance(value, _StrToken):
        try:
            return _coerce_leaf(tp_v, value, path) == v
        except (TypeCoercionError, ValueError, TypeError):
            return False
    return False


def _match_literal_str_token(vals: tuple[Any, ...], value: _StrToken, path: str) -> Any:
    """Try to match a _StrToken against Literal members; return the matched member or raise."""
    s = str(value)

    if s.lower() in _NONE_TOKENS:
        for v in vals:
            if v is None:
                return v

    for v in _steal_order([v for v in vals if v is not None], key=type):
        if _match_literal_member(v, value, path):
            return v

    raise TypeCoercionError.cannot_coerce(_src_type(value), value, f"Literal{vals}", path)


def _coerce_literal_value(tp: Any, value: Any, path: str) -> Any:
    """Coerce a raw value to a Literal type.

    Tokens are matched through the stealing rule; native file values keep
    declaration order. Both use ``_match_literal_member`` — one rule — so a
    ``Literal`` over ``Enum`` accepts the same text in both channels.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#stealing-rule
    """
    vals = _literal_values(tp)
    if isinstance(value, _StrToken):
        return _match_literal_str_token(vals, value, path)
    for v in vals:
        if _match_literal_member(v, value, path):
            return v
    raise TypeCoercionError.cannot_coerce(_src_type(value), value, f"Literal{vals}", path)


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


def _is_struct_variant(tp: Any) -> bool:
    """True if tp is a struct for dispatch and union disambiguation — a registered leaf is not.

    The single answer to "does this type get taken apart into fields?", asked by the
    construction and serialization dispatchers and by both sides' union-variant filters.
    Plain ``_is_struct`` is not that answer: a registered leaf may well have an ``__init__``
    (``UUID`` does, with a default for every parameter), and counting one as a struct variant
    both refuses unions that are not ambiguous and tags dumps that need no tag.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#leaf-coercion
    """
    return _is_struct(tp) and not _is_registered_leaf(tp)


def _is_taggable_leaf(tp: Any) -> bool:
    """True if tp is a registered leaf whose fields an explicit union tag may still name.

    The complement of ``_is_struct_variant``: a registered leaf is opaque to every implicit
    decision, but a tag naming its class builds it from its ``__init__`` parameters.

    Dev Notes:
        docs-dev/architecture/10-design-decisions.md#an-explicit-tag-opts-a-leaf-back-in
    """
    return _is_registered_leaf(tp) and _is_struct(tp)


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

    Handles bool, int, float, str, NoneType, ``Final[T]``, Literal, Enum, and registered
    leaf types (``Path`` and any type passed to ``confarg.register_leaf_type``). Only
    string tokens from the CLI, env vars or CSV files are parsed from text; any other
    value must already have the target type.

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
    unchanged for construct() to handle.  Never raises: a failed coercion also
    returns the token.  Expression tokens are always returned unchanged.

    Dev Notes:
        docs-dev/architecture/07-expressions.md#deferral-rule
    """
    if ft is None:
        return token
    if contains_expression(token):
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

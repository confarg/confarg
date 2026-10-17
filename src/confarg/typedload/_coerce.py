# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Leaf value coercion."""

from __future__ import annotations

import enum
import re
import types
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Callable

from confarg._import import _import_dotted, dotted_name
from confarg._types import (
    _is_callable,
    _is_dict,
    _is_enum,
    _is_frozenset,
    _is_list,
    _is_literal,
    _is_namedtuple,
    _is_none_type,
    _is_set,
    _is_struct,
    _is_tuple,
    _is_union,
    _literal_values,
    _resolve_type,
    _src_type,
    _StrToken,
    _type_ref_constraint,
    _union_args_no_none,
)
from confarg.dictexpr import contains_expression
from confarg.exceptions import SymbolImportError, SymbolNotFoundError, TypeCoercionError

_TRUTHY = frozenset({"true", "1", "yes", "on"})
_FALSY = frozenset({"false", "0", "no", "off"})
_NONE_TOKENS = frozenset({"none", "null"})


def _coerce_decimal(value: Any) -> Decimal:
    """Read a ``Decimal`` from text, an int or a float, a float through its shortest ``repr``.

    Raises:
        TypeError: If *value* is a bool or no str, int or float.
        ValueError: If the text spells no decimal.

    Dev Notes:
        docs-dev/architecture/design-decisions/decimal-and-uuid-are-built-in-leaves.md#a-files-float-reads-as-it-is-written
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError(value)
    try:
        return Decimal(repr(value) if isinstance(value, float) else value)
    except InvalidOperation:
        raise ValueError(value) from None


def _coerce_uuid(value: Any) -> UUID:
    """Read a ``UUID`` from its text, in any spelling ``UUID()`` reads.

    Raises:
        TypeError: If *value* is no str.
        ValueError: If the text spells no UUID.
    """
    if not isinstance(value, str):
        raise TypeError(value)
    return UUID(value)


class _LeafRefusal(ValueError):
    """A built-in leaf's refusal of a value, carrying the *hint* its error message ends with."""

    def __init__(self, hint: str) -> None:
        super().__init__(hint)
        self.hint = hint


def _base_60(n: int) -> str:
    """Spell *n* as the colon-separated base-60 number YAML 1.1 reads as it: 620 is ``10:20``."""
    digits: list[int] = []
    while n:
        n, digit = divmod(n, 60)
        digits.append(digit)
    head, *tail = reversed(digits)
    return ":".join([str(head), *(f"{d:02d}" for d in tail)])


def _refusal(hint: str, value: Any, *, yaml_base_60: bool = False, remedy: str = "") -> _LeafRefusal:
    """Return the refusal of *value* ending with *hint*, and, with *yaml_base_60*, YAML's reading of an int.

    An int of 60 or more may be what YAML 1.1 made of an unquoted ``10:20``, so the message
    spells it back that way, followed by *remedy*.
    """
    if yaml_base_60 and type(value) is int and value >= 60:  # noqa: PLR2004  # the first base-60 number with a colon
        hint += f"; YAML reads an unquoted {_base_60(value)} as the base-60 number {value}{remedy}"
    return _LeafRefusal(hint)


_DATE_HINT = "a date is ISO 8601 text, such as '2021-02-03'"
_DATETIME_HINT = "a datetime is ISO 8601 text, such as '2021-02-03T10:20:30+02:00'"
_TIME_HINT = "a time is ISO 8601 text, such as '10:20:30'"
_DURATION_HINT = "a duration is ISO 8601 text, such as 'PT1H30M'"
_OFFSET_HINT = "a timezone is an ISO 8601 offset, such as '+02:00' or 'Z'"


def _coerce_date(value: Any) -> date:
    """Read a ``date`` from the text ``date.fromisoformat`` reads.

    A ``datetime`` is refused, a midnight one included, as its text is.

    Raises:
        _LeafRefusal: If *value* is no str, or the text spells no date.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-files-native-value-reads-as-its-text
    """
    if not isinstance(value, str):
        raise _refusal(_DATE_HINT, value)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _refusal(_DATE_HINT, value) from None


def _coerce_datetime(value: Any) -> datetime:
    """Read a ``datetime`` from the text ``datetime.fromisoformat`` reads, or a ``date`` as its midnight.

    Raises:
        _LeafRefusal: If *value* is no str and no date, or the text spells no datetime.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-files-native-value-reads-as-its-text
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        raise _refusal(_DATETIME_HINT, value)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise _refusal(_DATETIME_HINT, value) from None


def _coerce_time(value: Any) -> time:
    """Read a ``time`` from the text ``time.fromisoformat`` reads.

    Raises:
        _LeafRefusal: If *value* is no str, or the text spells no time; an int may be YAML's
            base-60 reading of an unquoted time, which the hint says.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-number-is-no-time-and-no-duration
    """
    if not isinstance(value, str):
        raise _refusal(_TIME_HINT, value, yaml_base_60=True, remedy=", so quote it")
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise _refusal(_TIME_HINT, value) from None


_DURATION_NUMBER = r"\d+(?:[.,]\d+)?"
_DURATION_UNITS = {"W": 7 * 86_400_000_000, "D": 86_400_000_000, "H": 3_600_000_000, "M": 60_000_000, "S": 1_000_000}
_DURATION = re.compile(
    rf"(?P<sign>-)?P(?!$)(?:(?P<W>{_DURATION_NUMBER})W)?(?:(?P<D>{_DURATION_NUMBER})D)?"
    rf"(?:T(?!$)(?:(?P<H>{_DURATION_NUMBER})H)?(?:(?P<M>{_DURATION_NUMBER})M)?(?:(?P<S>{_DURATION_NUMBER})S)?)?",
    re.IGNORECASE,
)


def _parse_duration(text: str) -> timedelta:
    """Read the ISO 8601 duration *text* in its fixed units: ``[-]P[<n>W][<n>D][T[<n>H][<n>M][<n>S]]``.

    Case-insensitive; only the last part may carry a fraction, after ``.`` or ``,``. The sum
    is exact, rounded half-even to the microsecond as ``timedelta`` rounds.

    Raises:
        ValueError: If *text* is no such duration, or one ``timedelta`` cannot hold.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-duration-is-iso-8601-text
    """
    match = _DURATION.fullmatch(text)
    if match is None:
        raise ValueError(text)
    parts = [(unit, match[unit]) for unit in _DURATION_UNITS if match[unit] is not None]
    if any(not number.isdigit() for _, number in parts[:-1]):
        raise ValueError(text)
    micros = sum(Fraction(number.replace(",", ".")) * _DURATION_UNITS[unit] for unit, number in parts)
    try:
        duration = timedelta(microseconds=round(micros))
    except OverflowError:
        raise ValueError(text) from None
    return -duration if match["sign"] else duration


def _format_duration(value: timedelta) -> str:
    """Write *value* as the ISO 8601 duration :func:`_parse_duration` reads back: ``P1DT2H``, ``-PT1M30.5S``.

    Days, then hours, minutes and seconds, a zero part left out, the seconds' fraction
    trimmed; a negative duration is a minus before its length, and zero is ``PT0S``.
    """
    micros = value // timedelta(microseconds=1)
    sign, micros = ("-" if micros < 0 else ""), abs(micros)
    seconds, fraction = divmod(micros, 1_000_000)
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, seconds = divmod(seconds, 60)
    clock = f"{hours}H" if hours else ""
    clock += f"{minutes}M" if minutes else ""
    if seconds or fraction:
        clock += f"{seconds}" + (f".{fraction:06d}".rstrip("0") if fraction else "") + "S"
    if not (days or clock):
        return "PT0S"
    return f"{sign}P" + (f"{days}D" if days else "") + (f"T{clock}" if clock else "")


def _coerce_timedelta(value: Any) -> timedelta:
    """Read a ``timedelta`` from an ISO 8601 duration (:func:`_parse_duration`); a number is refused.

    Raises:
        _LeafRefusal: If *value* is no str, or the text spells no duration; an int may be
            YAML's base-60 reading of an unquoted ``1:30:00``, which the hint says.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-number-is-no-time-and-no-duration
    """
    if not isinstance(value, str):
        raise _refusal(_DURATION_HINT, value, yaml_base_60=True)
    try:
        return _parse_duration(value)
    except ValueError:
        raise _refusal(_DURATION_HINT, value) from None


def _coerce_timezone(value: Any) -> timezone:
    """Read a fixed-offset ``timezone`` from the UTC offset ``datetime.fromisoformat`` reads: ``Z``, ``+02:00``.

    ``Z`` is read in either case.

    Raises:
        _LeafRefusal: If *value* is no str, or the text spells no offset.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-timezone-is-an-iso-8601-offset
    """
    if not isinstance(value, str) or value[:1] not in {"+", "-", "Z", "z"}:
        raise _refusal(_OFFSET_HINT, value)
    try:
        offset = datetime.fromisoformat(f"2000-01-01T00:00{value.upper()}").tzinfo
    except ValueError:
        raise _refusal(_OFFSET_HINT, value) from None
    if not isinstance(offset, timezone):  # pragma: no cover  # fromisoformat reads an offset as a timezone
        raise _refusal(_OFFSET_HINT, value)
    return offset


def _format_offset(value: timezone) -> str:
    """Write *value* as the UTC offset ``datetime.isoformat()`` writes: ``+02:00``, ``+00:00``, ``+00:00:30``."""
    return datetime.min.replace(tzinfo=value).isoformat()[len("0001-01-01T00:00:00") :]


# register_leaf_type writes both registries at runtime, so nothing that reads them is ever
# cached: not _is_registered_leaf, _is_struct_variant, _is_taggable_leaf, _is_eagerly_coercible
# nor _type_kind (docs-dev/architecture/types/introspection.md#introspection-is-cached-per-class).
_LEAF_COERCIONS: dict[type, Any] = {
    Path: Path,
    Decimal: _coerce_decimal,
    UUID: _coerce_uuid,
    date: _coerce_date,
    datetime: _coerce_datetime,
    time: _coerce_time,
    timedelta: _coerce_timedelta,
    timezone: _coerce_timezone,
}
#: A Path is written with forward slashes, which every OS reads, so a dump is portable; a
#: Decimal and a UUID as their str(), the date and time types as ISO 8601 text: each as the
#: text its coercion reads back.
_LEAF_SERIALIZERS: dict[type, Any] = {
    Path: Path.as_posix,
    Decimal: str,
    UUID: str,
    date: date.isoformat,
    datetime: datetime.isoformat,
    time: time.isoformat,
    timedelta: _format_duration,
    timezone: _format_offset,
}


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
    """Coerce a dotted-path string or class object to a class, validated against type[X].

    Any string is read, a token or a file's text alike: a dotted path is recognized, never
    converted, so a file sets a ``type`` field as the CLI does and reads back its own dump.

    Raises:
        TypeCoercionError: If *value* is no class and no string, if nothing answers to the
            path, or if the class is not one *tp* admits.
        SymbolImportError: If a module on the path exists but fails while it is imported: the
            path names real code, so a union's other variants do not get to read it as text.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#stealing-rule
        docs-dev/architecture/types/dotted-imports.md#a-path-names-nothing-or-a-module-fails
    """
    if isinstance(value, type):
        constraint = _type_ref_constraint(tp)
        if constraint is not object and not issubclass(value, constraint):
            raise TypeCoercionError.not_a_subclass(dotted_name(value), dotted_name(constraint), path)
        return value
    if not isinstance(value, str):
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "type", path)
    try:
        obj = _import_dotted(str(value))
    except SymbolNotFoundError as e:
        msg = (
            f"Cannot import class {str(value)!r} at '{path}': {e}."
            f" Use a fully-qualified dotted path, e.g. 'mypackage.MyClass'."
        )
        raise TypeCoercionError(msg) from e
    except SymbolImportError as e:
        msg = f"Cannot import class {str(value)!r} at '{path}': {e}"
        raise SymbolImportError(msg) from e
    if not isinstance(obj, type):
        msg = f"Cannot coerce {str(value)!r} at '{path}': expected a class, got {type(obj).__name__!r}."
        raise TypeCoercionError(msg)
    constraint = _type_ref_constraint(tp)
    if constraint is not object and not issubclass(obj, constraint):
        raise TypeCoercionError.not_a_subclass(str(value), dotted_name(constraint), path)
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


_RANKED_LEAF_TYPES: tuple[type, ...] = (float, int, bool, types.NoneType, str)

#: Rank of each ranked leaf type. Dict lookup on a type object is identity-based: ``bool`` is
#: a subclass of ``int`` and ranks on its own.
_LEAF_TYPE_RANKS: dict[type, int] = {tp: 4 + i for i, tp in enumerate(_RANKED_LEAF_TYPES)}

#: A Callable's rank: below the kinds that recognize a narrower set, a class (type references)
#: or listed members (``Literal``), since a Callable takes anything callable, classes included.
_CALLABLE_RANK = 3


#: The lowest rank an object kind (:func:`_reads_as_object`) holds: a registered leaf ranks 0, an
#: Enum 1, a ``Literal`` over an Enum 2. Every rank after it is a kind an expression reads as
#: written: a Callable, which the reading never builds, and the kinds whose value a file holds.
_LAST_OBJECT_RANK = 2


def _steal_rank(tp: Any) -> int:
    """Return the stealing priority of a leaf type — lower steals first.

    A registered leaf ranks first, then ``Enum``, then every kind the rule does not name
    (type references, ``Literal``, a ``bytes`` Literal member), then a Callable, then float,
    int, bool, None and str. Types sharing a rank keep their declaration order,
    ``_steal_order`` being stable.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#stealing-rule
    """
    if _is_registered_leaf(tp):
        return 0
    if _is_enum(tp):
        return 1
    if _is_callable(tp):
        return _CALLABLE_RANK
    return _LEAF_TYPE_RANKS.get(tp, 2)


def _steal_order(variants: list[Any], *, key: Any) -> list[Any]:
    """Sort variants into stealing priority, declaration order breaking ties.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#stealing-rule

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
        docs-dev/architecture/types/stealing-rule.md#stealing-rule
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

    Every value meets the members in stealing rank, a token and a file's value alike, through
    ``_match_literal_member`` — one rule — so a ``Literal`` over ``Enum`` accepts the same
    text in both channels and reads it as the same member. Only a token reads a none word.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#stealing-rule
    """
    vals = _literal_values(tp)
    if isinstance(value, _StrToken):
        return _match_literal_str_token(vals, value, path)
    for v in _steal_order(list(vals), key=type):
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


def _registered_leaf_of(value: Any) -> type | None:
    """Return the registered leaf type *value* is an instance of, the most specific one; None if none.

    A ``datetime`` is a ``datetime``, not the ``date`` it subclasses, and a ``WindowsPath`` a
    ``Path``: the first registered class in the value's MRO. The one answer to "which leaf
    is this value?", asked when an instance passes through coercion and when it is serialized.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#an-instance-is-its-most-specific-registered-type
    """
    return next((cls for cls in type(value).__mro__ if cls in _LEAF_COERCIONS), None)


def _is_struct_variant(tp: Any) -> bool:
    """True if tp is a struct for dispatch and union disambiguation — a registered leaf is not.

    The single answer to "does this type get taken apart into fields?", asked by the
    construction and serialization dispatchers and by both sides' union-variant filters.
    Plain ``_is_struct`` is not that answer: a registered leaf may well have an ``__init__``
    (``UUID`` does, with a default for every parameter), and counting one as a struct variant
    both refuses unions that are not ambiguous and tags dumps that need no tag.

    Dev Notes:
        docs-dev/architecture/types/leaf-coercion.md#leaf-coercion
    """
    return _is_struct(tp) and not _is_registered_leaf(tp)


def _is_taggable_leaf(tp: Any) -> bool:
    """True if tp is a registered leaf whose fields an explicit union tag may still name.

    The complement of ``_is_struct_variant``: a registered leaf is opaque to every implicit
    decision, but a tag naming its class builds it from its ``__init__`` parameters.

    Dev Notes:
        docs-dev/architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in
    """
    return _is_registered_leaf(tp) and _is_struct(tp)


class _TypeKind(enum.Enum):
    """The shape a type dispatches as: one member per branch of a shape dispatch."""

    ANY = enum.auto()
    UNION = enum.auto()
    NAMEDTUPLE = enum.auto()
    STRUCT = enum.auto()
    TAGGABLE_LEAF = enum.auto()
    LIST = enum.auto()
    SET = enum.auto()
    FROZENSET = enum.auto()
    TUPLE = enum.auto()
    DICT = enum.auto()
    CALLABLE = enum.auto()
    LEAF = enum.auto()


# The order the shape predicates are asked in, first match winning; a type none of them
# names is a LEAF. Every shape dispatch reads it through _type_kind, so none restates it.
_KIND_ORDER: tuple[tuple[Callable[[Any], bool], _TypeKind], ...] = (
    (lambda tp: tp is Any, _TypeKind.ANY),
    (_is_union, _TypeKind.UNION),
    (_is_namedtuple, _TypeKind.NAMEDTUPLE),
    (_is_struct_variant, _TypeKind.STRUCT),
    (_is_taggable_leaf, _TypeKind.TAGGABLE_LEAF),
    (_is_list, _TypeKind.LIST),
    (_is_set, _TypeKind.SET),
    (_is_frozenset, _TypeKind.FROZENSET),
    (_is_tuple, _TypeKind.TUPLE),
    (_is_dict, _TypeKind.DICT),
    (_is_callable, _TypeKind.CALLABLE),
)


def _type_kind(tp: Any) -> _TypeKind:
    """Return the shape *tp* dispatches as, its wrappers unwrapped.

    The one answer construction, serialization, the union-variant test and the CLI type
    walk dispatch on, so every type takes the same branch in each. A struct is ``STRUCT`` by
    :func:`_is_struct_variant` and ``TAGGABLE_LEAF`` by :func:`_is_taggable_leaf`.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#shape-dispatch
    """
    tp = _resolve_type(tp)
    return next((kind for holds, kind in _KIND_ORDER if holds(tp)), _TypeKind.LEAF)


_SCALAR_COERCIONS: dict[type, Any] = {
    bool: _coerce_bool_value,
    int: _coerce_int_value,
    float: _coerce_float_value,
    str: _coerce_str_value,
}


def _is_coercible_leaf(tp: Any) -> bool:
    """True if :func:`_coerce_leaf` coerces a value to the resolved leaf type *tp*.

    The one answer to "Unsupported leaf type": construction refuses every other leaf, and
    ``dump()`` refuses to write a value typed by one, since it would not read back.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#an-unsupported-leaf-is-refused-both-ways
    """
    return (
        tp is Any
        or _is_none_type(tp)
        or tp in _SCALAR_COERCIONS
        or _is_literal(tp)
        or _is_enum(tp)
        or tp in _LEAF_COERCIONS
    )


def _coerce_registered(tp: Any, value: Any, path: str) -> Any:
    """Coerce value to a type registered in _LEAF_COERCIONS, passing its own instances through.

    An instance passes through when *tp* is its most specific registered type
    (:func:`_registered_leaf_of`), so a ``datetime`` meets the ``date`` coercion, which refuses it.
    """
    if _registered_leaf_of(value) is tp:
        return value
    try:
        return _LEAF_COERCIONS[tp](value)
    except _LeafRefusal as exc:
        raise TypeCoercionError.cannot_coerce_because(_src_type(value), value, tp.__name__, path, exc.hint) from None
    except (TypeError, ValueError, OSError):
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, tp.__name__, path) from None


def _reads_as_object(tp: Any) -> bool:
    """True if a value of the leaf type *tp* is an object no configuration file holds.

    An Enum member, an instance of a registered leaf type, and a ``Literal`` member that is
    one: a file holds such a value as the text or the number ``dump()`` writes for it. The
    one answer for both sides of it: a parser leaves such a token as written
    (:func:`_is_eagerly_coercible`), and an expression reads the leaf as its object
    (:func:`read_as_object`).

    Dev Notes:
        docs-dev/architecture/types/token-model.md#a-leaf-reaches-the-merged-dict-as-written
    """
    return (
        _is_enum(tp)
        or tp in _LEAF_COERCIONS
        or (_is_literal(tp) and any(isinstance(v, enum.Enum) for v in _literal_values(tp)))
    )


def _is_eagerly_coercible(tp: Any) -> bool:
    """True if a string token for *tp* should be coerced before ``build()``.

    The leaf types whose coerced value is one a file holds natively, so a token holds in the
    merged dict what a file would: the scalar numbers (bool, int, float), None, and a
    Literal over them. ``str`` is excluded — a ``str`` token is already a str subclass and
    passes through — and so is a type whose value is an object no file holds
    (:func:`_reads_as_object`), which stays as written. This mirrors the branches of
    :func:`_coerce_leaf`; the two diverge on raise-vs-return, so share only the predicate,
    not the behavior.

    Dev Notes:
        docs-dev/architecture/expressions/deferral-rule.md#deferral-rule
        docs-dev/architecture/types/token-model.md#a-leaf-reaches-the-merged-dict-as-written
    """
    return (_is_literal(tp) or tp in (bool, int, float) or _is_none_type(tp)) and not _reads_as_object(tp)


def _certain_leaf(ft: Any) -> Any:
    """Return the one type a leaf of field type *ft* is coerced to, None for a union of several.

    An optional is its one other variant; any other union is construction's to decide, by
    the value it is given.
    """
    ft = _resolve_type(ft)
    if not _is_union(ft):
        return ft
    non_none = _union_args_no_none(ft)
    return _resolve_type(non_none[0]) if len(non_none) == 1 else None


def read_as_object(ft: Any, value: Any) -> Any:
    """Return what an expression reads of *value*, at a field of type *ft*: the object, where one is certain.

    Where *ft* is one type whose value is an object no file holds (:func:`_reads_as_object`),
    an optional included, *value* is read as that object, whichever channel wrote it and
    however it spelled it: ``RED``, ``red`` and ``Color.RED`` are one member. Anywhere else,
    and for a value the type refuses, *value* is read as written: construction refuses it. A
    union of several variants is read by the variant construction picks, which
    ``_typed_read`` asks :func:`~confarg.typedload._construct.read_union_leaf` for.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
    """
    tp = _certain_leaf(ft)
    if tp is None or not _reads_as_object(tp) or contains_expression(value):
        return value
    try:
        return _coerce_leaf(tp, value)
    except TypeCoercionError:
        return value


def _held_by_any(value: Any) -> Any:
    """Return what an ``Any`` leaf holds of *value*: the value itself, a token as its text.

    The leaf half of what an ``Any`` node holds, construction's and a dict key's alike: a
    token, a CSV cell's keys included, becomes the plain ``str`` it spells. A container is
    construction's to walk, each item an ``Any`` node in turn
    (:func:`~confarg.typedload._construct._construct_any`).

    Dev Notes:
        docs-dev/architecture/types/leaf-coercion.md#leaf-coercion
    """
    return str(value) if isinstance(value, _StrToken) else value


def _coerce_leaf(tp: Any, value: Any, path: str = "") -> Any:  # noqa: PLR0911  # one branch per leaf type
    """Coerce a raw value to the target leaf type.

    Handles bool, int, float, str, NoneType, Literal, Enum, Any, and registered
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
    if not _is_coercible_leaf(tp):
        msg = f"Unsupported leaf type {tp} at '{path}'"
        raise TypeCoercionError(msg)
    if tp is Any:
        return _held_by_any(value)
    if _is_none_type(tp):
        if value is None:
            return None
        if isinstance(value, _StrToken) and (str(value).lower() in _NONE_TOKENS or str(value) == ""):
            return None
        raise TypeCoercionError.cannot_coerce(_src_type(value), value, "None", path)
    if tp in _SCALAR_COERCIONS:
        return _SCALAR_COERCIONS[tp](value, path)
    if _is_literal(tp):
        return _coerce_literal_value(tp, value, path)
    if _is_enum(tp):
        return _coerce_enum_value(tp, value, path)
    return _coerce_registered(tp, value, path)


def _try_coerce(ft: Any, token: _StrToken) -> Any:
    """Coerce a string token to the target type if unambiguous.

    Coerces immediately to a value a file holds natively (:func:`_is_eagerly_coercible`:
    bool, int, float, None, a Literal over them) so the merged dict holds what a file
    would.  str tokens are returned unchanged — _StrToken is already a str subclass — and
    so are tokens for an Enum or a registered leaf type, which a file holds as text too.
    For multi-variant unions, returns token unchanged for construct() to handle.  Never
    raises: a failed coercion also returns the token.  Expression tokens are always
    returned unchanged.

    Dev Notes:
        docs-dev/architecture/expressions/deferral-rule.md#deferral-rule
        docs-dev/architecture/types/token-model.md#a-leaf-reaches-the-merged-dict-as-written
    """
    if ft is None or contains_expression(token):
        return token
    tp = _certain_leaf(ft)
    if tp is None or not _is_eagerly_coercible(tp):
        return token
    try:
        return _coerce_leaf(tp, token)
    except TypeCoercionError:
        return token

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for _construct: struct dispatch, union fallbacks and the all-default shortcut."""

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import pytest

import confarg
from confarg._types import _StrToken, _UnionSeqToken
from confarg.exceptions import MissingFieldError, TypeCoercionError
from confarg.typedload._construct import _construct_struct_dispatch, construct

# Each scenario uses its own base class so __subclasses__() does not bleed across tests.


@dataclass
class _BaseWithSubs:
    """Base whose subclasses have disjoint required fields."""


@dataclass
class _Sub1(_BaseWithSubs):
    x: str


@dataclass
class _Sub2(_BaseWithSubs):
    y: int


@dataclass
class _BaseNoSubs:
    """Base with no subclasses — can be constructed directly."""

    value: int = 0


class TestConstructStructDispatch:
    """_construct_struct_dispatch raises when subclasses exist but no union_tag is given."""

    def test_subclasses_without_tag_raises(self) -> None:
        """When a struct has subclasses and no union_tag is present, raise TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="discriminator"):
            _construct_struct_dispatch(_BaseWithSubs, {"x": _StrToken("hello")}, "", "class")

    def test_subclasses_with_tag_constructs(self) -> None:
        """When the union_tag is present, the named subclass is constructed."""
        result = _construct_struct_dispatch(
            _BaseWithSubs,
            {"class": f"{__name__}._Sub1", "x": _StrToken("hello")},
            "",
            "class",
        )
        assert isinstance(result, _Sub1)
        assert result.x == "hello"

    def test_no_subclasses_constructs_directly(self) -> None:
        """When the struct has no subclasses, it is constructed directly without a tag."""
        result = _construct_struct_dispatch(_BaseNoSubs, {}, "", "class")
        assert result == _BaseNoSubs()


class TestUnionSeqTokenFallback:
    """A _UnionSeqToken (a lone CLI token) falls back to the sequence variant.

    A plain _StrToken (env/config scalar) does not — gating the fallback to the
    CLI-only marker keeps env/config strict.
    """

    def test_unmatched_scalar_fills_sequence_variant(self) -> None:
        """Bool rejects 'hello', so the marked token fills list[str] as ['hello']."""
        assert construct(bool | list[str], _UnionSeqToken("hello")) == ["hello"]

    def test_matched_scalar_keeps_scalar_priority(self) -> None:
        """'true' matches the bool variant first; no list wrapping happens."""
        assert construct(bool | list[str], _UnionSeqToken("true")) is True

    def test_plain_strtoken_does_not_fall_back(self) -> None:
        """A plain _StrToken (env/config scalar) stays strict: no sequence fallback."""
        with pytest.raises(TypeCoercionError):
            construct(bool | list[str], _StrToken("hello"))


class _TypeStealTarget:
    """Module-level class used as a dotted-path target for str | type stealing tests."""


class TestUnionTypeRefStealing:
    """A type-ref variant participates in the stealing rule, taking priority over str.

    Regression: _coerce_scalar_variants coerced each variant with _coerce_leaf, which
    cannot build a type ref, so str always stole a str | type union. It now delegates
    to the canonical scalar constructor, letting `type` win.
    """

    def test_bare_builtin_steals_over_str(self) -> None:
        """'int' resolves to the int class for str | type, not the string 'int'."""
        assert construct(str | type, _StrToken("int")) is int

    def test_dotted_path_steals_over_str(self) -> None:
        """A dotted class path resolves to the class for str | type, not the string."""
        path = f"{_TypeStealTarget.__module__}.{_TypeStealTarget.__qualname__}"
        assert construct(str | type, _StrToken(path)) is _TypeStealTarget

    def test_unresolvable_value_falls_back_to_str(self) -> None:
        """A value that is no importable type stays a str (str is the least-priority variant)."""
        assert construct(str | type, _StrToken("not.a.real.class")) == "not.a.real.class"

    def test_constrained_type_ref_steals_over_str(self) -> None:
        """A type[Base] variant also steals: a subclass dotted path resolves to the class."""
        assert construct(str | type[_TypeStealTarget], _StrToken("int")) == "int"  # int not a subclass → str wins
        path = f"{_TypeStealTarget.__module__}.{_TypeStealTarget.__qualname__}"
        assert construct(str | type[_TypeStealTarget], _StrToken(path)) is _TypeStealTarget


@dataclass
class _NeedsIdent:
    """A required field typed as an unregistered class with an all-default __init__."""

    ident: UUID


@dataclass
class _AllDefaults:
    """A struct that really can be built from nothing."""

    n: int = 1


@dataclass
class _NeedsAllDefaults:
    """A required field whose type is a struct that really can be built from nothing."""

    nested: _AllDefaults


class TestAllDefaultShortcut:
    """A missing field is built from {} only if that works; otherwise it stays missing.

    ``_all_have_defaults`` reads ``__init__`` parameter defaults, which is not the same
    question as "does ``tp()`` work": ``UUID`` defaults all seven of its parameters and
    still refuses an empty call. The shortcut is a guess, so its ``TypeError`` means the
    guess was wrong, not that the user gets a stdlib traceback out of ``build()``.
    """

    def test_constructor_refusing_empty_call_is_a_missing_field(self) -> None:
        """An unregistered all-default-__init__ class that refuses {} is a MissingFieldError."""
        with pytest.raises(MissingFieldError, match="ident"):
            confarg.build(_NeedsIdent, {})

    def test_message_matches_the_plain_missing_field_message(self) -> None:
        """The message is the one any other missing field gets, naming type and flag."""
        with pytest.raises(MissingFieldError) as exc_info:
            confarg.build(_NeedsIdent, {})
        msg = str(exc_info.value)
        assert repr(UUID) in msg
        assert "--ident" in msg

    def test_buildable_struct_is_still_auto_created(self) -> None:
        """The shortcut itself is intact: a struct that accepts {} is still built from it."""
        assert confarg.build(_NeedsAllDefaults, {}) == _NeedsAllDefaults(nested=_AllDefaults())


# ---------------------------------------------------------------------------
# Stealing order
# ---------------------------------------------------------------------------


class _Word:
    """Registered leaf type accepting any text — a leaf that outranks every other kind."""

    def __init__(self, text: str) -> None:
        self.text = str(text)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Word) and other.text == self.text

    def __hash__(self) -> int:
        return hash(self.text)


class _Grade(enum.Enum):
    """Enum whose member names and values collide with other leaf kinds."""

    FOO = 1
    BAR = 2


@pytest.fixture
def _registered(leaf_registry: None) -> None:
    """Register the leaf types the ordering tests rank, undone after the test."""
    confarg.register_leaf_type(Decimal, Decimal)
    confarg.register_leaf_type(_Word, _Word)


class TestStealOrder:
    """A token meeting a union of leaves is taken by rank, never by declaration order.

    The rank is ``registered leaf > Enum > everything else > float > int > bool > None > str``;
    each pair below is written in both declaration orders, since the point of the rule is that
    the order a union is spelled in does not decide.
    """

    @pytest.mark.usefixtures("_registered")
    @pytest.mark.parametrize("tp", [int | Decimal, Decimal | int])
    def test_registered_leaf_steals_over_int(self, tp: Any) -> None:
        """A registered leaf outranks int whichever side of the union it is written on."""
        result = construct(tp, _StrToken("5"))
        assert result == Decimal(5)
        assert type(result) is Decimal

    @pytest.mark.usefixtures("_registered")
    @pytest.mark.parametrize("tp", [_Grade | _Word, _Word | _Grade])
    def test_registered_leaf_steals_over_enum(self, tp: Any) -> None:
        """A registered leaf outranks an Enum, even on a token naming a member."""
        assert construct(tp, _StrToken("FOO")) == _Word("FOO")

    @pytest.mark.parametrize("tp", [float | _Grade, _Grade | float])
    def test_enum_steals_over_float(self, tp: Any) -> None:
        """An Enum outranks float: '1' is the member with value 1, not 1.0."""
        assert construct(tp, _StrToken("1")) is _Grade.FOO

    @pytest.mark.parametrize("tp", [int | Literal["5"], Literal["5"] | int])
    def test_literal_steals_over_int(self, tp: Any) -> None:
        """A Literal member outranks int: the kinds the rule does not name rank above it."""
        result = construct(tp, _StrToken("5"))
        assert result == "5"
        assert type(result) is str

    @pytest.mark.parametrize("tp", [int | float, float | int])
    def test_float_steals_over_int(self, tp: Any) -> None:
        """Float outranks int: an integral token still lands on the float variant."""
        result = construct(tp, _StrToken("5"))
        assert result == 5.0
        assert type(result) is float

    @pytest.mark.parametrize("tp", [bool | int, int | bool])
    def test_int_steals_over_bool_for_a_number(self, tp: Any) -> None:
        """Int outranks bool: '1' is the number one, not True."""
        result = construct(tp, _StrToken("1"))
        assert result == 1
        assert type(result) is int

    @pytest.mark.parametrize("tp", [bool | int, int | bool])
    def test_bool_takes_a_word_no_number_type_accepts(self, tp: Any) -> None:
        """Bool still takes a bool word: it is last of the numbers, not excluded."""
        assert construct(tp, _StrToken("yes")) is True

    @pytest.mark.parametrize("tp", [bool | float, float | bool])
    def test_float_steals_over_bool(self, tp: Any) -> None:
        """Float outranks bool the same way int does."""
        result = construct(tp, _StrToken("1"))
        assert result == 1.0
        assert type(result) is float

    @pytest.mark.parametrize("tp", [bool | None, None | bool])
    def test_bool_steals_over_none(self, tp: Any) -> None:
        """Bool outranks None, and None still takes a none word no other variant accepts."""
        assert construct(tp, _StrToken("off")) is False
        assert construct(tp, _StrToken("none")) is None

    @pytest.mark.parametrize("tp", [str | None, None | str])
    def test_none_steals_over_str(self, tp: Any) -> None:
        """None outranks str for a none word, and an empty token is still the empty string."""
        assert construct(tp, _StrToken("null")) is None
        assert construct(tp, _StrToken("")) == ""

    @pytest.mark.parametrize("tp", [int | str, str | int])
    def test_str_is_last(self, tp: Any) -> None:
        """Str takes only what no other variant accepts."""
        assert construct(tp, _StrToken("5")) == 5
        assert construct(tp, _StrToken("abc")) == "abc"

    @pytest.mark.parametrize("tp", [int | float, float | int])
    def test_native_values_keep_their_own_type(self, tp: Any) -> None:
        """The rank orders tokens only: a native value from a file is never re-interpreted."""
        assert type(construct(tp, 5)) is int
        assert type(construct(tp, 5.0)) is float

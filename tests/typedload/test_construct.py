# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for _construct: struct dispatch, union fallbacks and the all-default shortcut."""

import _thread
import enum
import random
import re
import sys
import threading
from collections.abc import Callable
from dataclasses import InitVar, dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, NamedTuple, Protocol
from uuid import UUID

import pytest

import confarg
from confarg._merge import (
    DICT_DELETE,
    MERGE_OP_KEYS,
    ListOp,
)
from confarg._types import _StrToken, _UnionSeqToken
from confarg.exceptions import ConfargWarning, MissingFieldError, SymbolImportError, TypeCoercionError
from confarg.typedload._construct import _construct_struct_dispatch, construct
from tests.conftest import OneOf

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
    """_construct_struct_dispatch raises when subclasses exist but no class key is given."""

    def test_subclasses_without_tag_raises(self) -> None:
        """When a struct has subclasses and no class key is present, raise TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="no 'class' key was provided"):
            _construct_struct_dispatch(_BaseWithSubs, {"x": _StrToken("hello")}, ())

    def test_subclasses_with_tag_constructs(self) -> None:
        """When the class key is present, the named subclass is constructed."""
        result = _construct_struct_dispatch(
            _BaseWithSubs,
            {"class": f"{__name__}._Sub1", "x": _StrToken("hello")},
            (),
        )
        assert isinstance(result, _Sub1)
        assert result.x == "hello"

    def test_no_subclasses_constructs_directly(self) -> None:
        """When the struct has no subclasses, it is constructed directly without a tag."""
        result = _construct_struct_dispatch(_BaseNoSubs, {}, ())
        assert result == _BaseNoSubs()


def _no_class_refusal(tp: str, why: str, tag: str, *, path: str = "x") -> str:
    """Return the refusal of a class key naming *tag* at *path* on *tp*, as written, which *why* explains."""
    return (
        f"Cannot coerce dict {{'class': {tag!r}}} to {tp} at '{path}'. The 'class' key picks the class"
        f" to build from the keys beside it, and {why}. A 'call:' spec computes a value the field's type accepts."
    )


class TestATagNoVariantTakes:
    """A union no variant of which a tag selects refuses the tag as a leaf does, importing nothing (BUG-252)."""

    @pytest.mark.parametrize(
        ("tp", "spelled", "why"),
        [
            pytest.param(int, "int", "int is built from one value, not from keys", id="leaf"),
            pytest.param(Path, "Path", "Path is built from one value, not from keys", id="untaggable-leaf"),
            pytest.param(datetime, "datetime", "datetime is built from one value, not from keys", id="registered-leaf"),
            pytest.param(int | str, "int | str", "no variant of int | str is built from keys", id="scalars"),
            pytest.param(
                int | Path, "int | Path", "no variant of int | Path is built from keys", id="untaggable-leaf-variant"
            ),
            pytest.param(
                int | datetime,
                "int | datetime",
                "no variant of int | datetime is built from keys",
                id="registered-leaf-variant",
            ),
        ],
    )
    def test_the_refusal_says_why_no_class_is_picked(self, tp: Any, spelled: str, why: str) -> None:
        """The leaf's refusal says it is built from one value, the union's that no variant is built from keys."""
        with pytest.raises(TypeCoercionError) as exc_info:
            construct(tp, {"class": "pathlib.Path"}, path=("x",))
        assert str(exc_info.value) == _no_class_refusal(spelled, why, "pathlib.Path")

    def test_the_tag_is_not_imported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
    ) -> None:
        """Every tag is refused, so none is imported: a module the tag names never runs."""
        (tmp_path / "bug252_broken.py").write_text("raise RuntimeError('boom')\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        request.addfinalizer(lambda: sys.modules.pop("bug252_broken", None))
        for tag in ("bug252_broken.Thing", "bug252_nothere.Thing"):
            with pytest.raises(TypeCoercionError) as exc_info:
                construct(int | str, {"class": tag}, path=("x",))
            assert str(exc_info.value) == _no_class_refusal(
                "int | str", "no variant of int | str is built from keys", tag
            )
        assert "bug252_broken" not in sys.modules


@dataclass
class _Bug276Job:
    """A class a tag selects beside a dict variant."""

    kind: str = "batch"


class _Bug276Pair(NamedTuple):
    """A namedtuple variant, which reads a dict as its fields."""

    a: str
    b: str


class TestATagSpelledKeyIsDataWhereNoTagSelects:
    """A union no tag selects a variant of reads the tag's spelling as data where a variant reads a dict (BUG-276).

    The union read the key as the tag whatever its variants were, so ``int | dict[str, str]``
    refused ``{class: confidential}``, which a lone ``dict[str, str]`` holds as an entry.
    """

    @pytest.mark.parametrize(
        "tp",
        [
            pytest.param(int | dict[str, str], id="scalar-and-dict"),
            pytest.param(list[str] | dict[str, str], id="list-and-dict"),
            pytest.param(dict[str, str] | None, id="optional-dict"),
            pytest.param(int | dict, id="untyped-dict"),
            pytest.param(Literal["x"] | dict[str, str], id="literal-and-dict"),
            pytest.param(int | datetime | dict[str, str], id="registered-leaf-built-from-one-value"),
        ],
    )
    def test_a_dict_variant_holds_the_key(self, tp: Any) -> None:
        """The dict variant takes ``class`` as an entry, as a lone dict does."""
        assert construct(tp, {"class": "confidential"}, path=("x",)) == {"class": "confidential"}

    def test_the_key_is_not_imported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
    ) -> None:
        """Data is never imported: a module the key's value names never runs."""
        (tmp_path / "bug276_broken.py").write_text("raise RuntimeError('boom')\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        request.addfinalizer(lambda: sys.modules.pop("bug276_broken", None))
        data = {"class": "bug276_broken.Thing"}
        assert construct(int | dict[str, str], data, path=("x",)) == data
        assert "bug276_broken" not in sys.modules

    @pytest.mark.parametrize(
        ("tp", "spelled"),
        [
            pytest.param(int | dict[int, str], "int | dict[int, str]", id="int-keyed-dict"),
            pytest.param(list[int] | str, "list[int] | str", id="sequence"),
            pytest.param(int | set[str], "int | set[str]", id="set"),
            pytest.param(tuple[str, str] | int, "tuple[str, str] | int", id="fixed-tuple"),
            pytest.param(_Bug276Pair | int, "_Bug276Pair | int", id="namedtuple"),
        ],
    )
    def test_a_variant_that_cannot_hold_the_key_refuses_it_as_data(self, tp: Any, spelled: str) -> None:
        """A variant reads the dict, so the key is data it refuses: the union's refusal, not the tag's."""
        with pytest.raises(TypeCoercionError) as exc_info:
            construct(tp, {"class": "x"}, path=("x",))
        assert str(exc_info.value).startswith(f"Cannot coerce dict {{'class': 'x'}} to {spelled} at 'x'")
        assert "picks the class" not in str(exc_info.value)

    @pytest.mark.parametrize(
        "tp",
        [
            pytest.param(_Bug276Job | dict[str, str], id="struct"),
            pytest.param(UUID | dict[str, str], id="registered-leaf-built-from-keys"),
            pytest.param(Any | dict[str, str], id="spec-reader"),
        ],
    )
    def test_a_variant_a_tag_selects_keeps_the_tag(self, tp: Any) -> None:
        """Beside a variant a tag selects the key is the tag: a class that does not import is refused."""
        with pytest.raises(TypeCoercionError, match="Cannot import class 'confidential'"):
            construct(tp, {"class": "confidential"}, path=("x",))


class _Bug261Color(enum.Enum):
    RED = "red"


class TestAUnionKeyType:
    """A dict keyed by a union reads each key as a union reads a token (BUG-261)."""

    @pytest.mark.parametrize(
        ("tp", "data", "expected"),
        [
            pytest.param(dict[int | None, int], {1: 5}, {1: 5}, id="native-int"),
            pytest.param(dict[int | None, int], {"null": 5, "none": 6}, {None: 6}, id="none-words-are-one-key"),
            pytest.param(dict[str | int, int], {"1": 5, "a": 6}, {1: 5, "a": 6}, id="rank-not-declaration-order"),
            pytest.param(
                dict[_Bug261Color | str, int], {"RED": 5, "x": 6}, {_Bug261Color.RED: 5, "x": 6}, id="enum-member"
            ),
        ],
    )
    def test_keys_read_as_a_union_reads_a_token(self, tp: Any, data: dict[Any, Any], expected: Any) -> None:
        """The text spelling a number is the number; a variant's member is the member; the rest is text."""
        assert construct(tp, data, path=("d",)) == expected

    def test_a_key_no_variant_takes_is_the_unions_refusal(self) -> None:
        """A key no variant reads is refused as the union refuses a value."""
        with pytest.raises(TypeCoercionError) as exc_info:
            construct(dict[int | None, int], {"x": 1}, path=("d",))
        assert str(exc_info.value) == "Cannot coerce str 'x' to int at 'd'"

    def test_a_key_refusal_offers_no_field_remedy(self) -> None:
        """A key is no field: the none-word remedy a field's token gets is left out, the variants' reasons kept."""
        with pytest.raises(TypeCoercionError) as exc_info:
            construct(dict[_Bug261Color | int | None, int], {"x": 1}, path=("d",))
        assert str(exc_info.value) == (
            "Cannot coerce str 'x' to _Bug261Color | int | None at 'd':\n  _Bug261Color: valid members 'RED' ('red')"
        )

    def test_a_variant_no_key_is_refuses_the_key_type(self) -> None:
        """A key type is a leaf construction reads, or a union of them, as ``dump()`` requires."""
        with pytest.raises(TypeCoercionError, match=re.escape("Unsupported leaf type int | tuple[int, int] at 'd'")):
            construct(dict[int | tuple[int, int], int], {"1": 1}, path=("d",))


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

    ident: OneOf


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
    question as "does ``tp()`` work": ``OneOf`` defaults both of its parameters and
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
        assert "of type OneOf." in msg
        assert "--ident" in msg

    def test_buildable_struct_is_still_auto_created(self) -> None:
        """The shortcut itself is intact: a struct that accepts {} is still built from it."""
        assert confarg.build(_NeedsAllDefaults, {}) == _NeedsAllDefaults(nested=_AllDefaults())

    def test_constructor_refusing_empty_call_is_a_missing_root(self) -> None:
        """The root takes the field's rule: a root that refuses {} is a missing root (BUG-184)."""
        with pytest.raises(MissingFieldError, match="No value provided for target type"):
            confarg.build(OneOf, {})

    def test_message_matches_the_scalar_root_message(self) -> None:
        """The message is the one a scalar target nothing supplied gets, naming the target type."""
        with pytest.raises(MissingFieldError) as exc_info:
            confarg.build(OneOf, {})
        msg = str(exc_info.value)
        assert "target type OneOf." in msg
        assert "--json <json>" in msg

    def test_buildable_root_is_still_built_from_nothing(self) -> None:
        """The shortcut itself is intact at the root: a struct that accepts {} still builds."""
        assert confarg.build(_AllDefaults, {}) == _AllDefaults()


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
    """Register the leaf type the ordering tests rank beside the built-in Decimal, undone after the test."""
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
        """Only a token is converted: a native number from a file is never re-interpreted."""
        assert type(construct(tp, 5)) is int
        assert type(construct(tp, 5.0)) is float


class _Level(enum.IntEnum):
    """Enum whose values a file holds as native integers."""

    ONE = 1
    FIVE = 5


class TestStealOrderForNativeValues:
    """A native value meets a union's leaf variants in the same rank a token does (BUG-230).

    Only a token is *converted*, to a number, a bool or ``None``; any value is *recognized* by a
    variant that names it, a type reference, an Enum member, a ``Literal`` member or a registered
    leaf. Each union is written in both declaration orders: the order decides nothing, for a
    file's value no more than for a token.
    """

    @pytest.mark.parametrize("tp", [str | type, type | str])
    def test_a_type_path_steals_over_str(self, tp: Any) -> None:
        """A file's dotted path to a class is the class, as the same text on the CLI is."""
        assert construct(tp, "builtins.int") is int

    @pytest.mark.parametrize("tp", [str | type, type | str])
    def test_a_string_naming_no_class_stays_a_str(self, tp: Any) -> None:
        """Text that imports nothing is left to the str variant."""
        assert construct(tp, "hello world") == "hello world"

    @pytest.mark.parametrize("tp", [str | _Grade, _Grade | str])
    def test_an_enum_steals_over_str(self, tp: Any) -> None:
        """A file's member name is the member, whichever side of the union the Enum is on."""
        assert construct(tp, "FOO") is _Grade.FOO

    @pytest.mark.parametrize("tp", [int | _Level, _Level | int])
    def test_an_enum_steals_a_native_number_over_int(self, tp: Any) -> None:
        """A file's number that is a member's value is the member, as the token '5' is."""
        assert construct(tp, 5) is _Level.FIVE

    @pytest.mark.usefixtures("_registered")
    @pytest.mark.parametrize("tp", [str | _Word, _Word | str])
    def test_a_registered_leaf_steals_over_str(self, tp: Any) -> None:
        """A registered leaf outranks str for a file's string too."""
        assert construct(tp, "abc") == _Word("abc")

    @pytest.mark.parametrize("tp", [Literal[_Grade.FOO, "FOO"], Literal["FOO", _Grade.FOO]])
    def test_an_enum_literal_member_steals_over_a_str_member(self, tp: Any) -> None:
        """The members of a Literal are ranked for a file's value as for a token."""
        assert construct(tp, "FOO") is _Grade.FOO

    @pytest.mark.parametrize("tp", [int | str, str | int])
    def test_a_file_string_is_never_converted_to_a_number(self, tp: Any) -> None:
        """No Norway problem: a file's "5" is text, only a token is converted."""
        assert construct(tp, "5") == "5"

    @pytest.mark.parametrize("tp", [str | None, None | str])
    def test_a_file_none_word_stays_a_str(self, tp: Any) -> None:
        """Only a token's none word selects None: a file writes None as its own null."""
        assert construct(tp, "none") == "none"

    @pytest.mark.parametrize("tp", [bool | _Level, _Level | bool])
    def test_a_native_bool_is_no_enum_value(self, tp: Any) -> None:
        """An Enum compares a native value by its exact type, so true never selects the member 1."""
        assert construct(tp, data=True) is True


class TestIntRanksAboveFloat:
    """A whole number is an ``int`` and anything else a ``float``, from a file and a token alike (BUG-154).

    ``float`` reads a file's ``int`` since BUG-154, so the rank alone decides ``int | float``; it puts
    ``int`` first, the more specific of the two. Each union is written in both declaration orders.
    """

    @pytest.mark.parametrize("tp", [int | float, float | int])
    @pytest.mark.parametrize("value", [1, _StrToken("1"), _StrToken("0x10")], ids=["native", "token", "token-hex"])
    def test_a_whole_number_is_an_int(self, tp: Any, value: Any) -> None:
        """A file's ``1`` and the token ``1`` are the same ``int``."""
        assert type(construct(tp, value)) is int

    @pytest.mark.parametrize("tp", [int | float, float | int])
    @pytest.mark.parametrize("value", [1.0, _StrToken("1.5"), _StrToken("1e3")], ids=["native", "token", "token-exp"])
    def test_any_other_number_is_a_float(self, tp: Any, value: Any) -> None:
        """A file's ``1.0`` and a token ``int`` refuses are the ``float``."""
        assert type(construct(tp, value)) is float

    @pytest.mark.parametrize("tp", [float | str, float | bool, float | None])
    def test_a_native_int_meets_the_float_variant(self, tp: Any) -> None:
        """Beside a variant that refuses it, a file's ``1`` is the ``float`` its token is."""
        built = construct(tp, 1)
        assert type(built) is float
        assert built == 1.0


class TestFloatHoldsANativeInt:
    """Every position a ``float`` leaf takes a file's ``int`` at builds the ``float`` (BUG-154)."""

    @pytest.mark.parametrize(
        ("tp", "data", "expected"),
        [
            (tuple[float, float], [0, 1], (0.0, 1.0)),
            (tuple[float, ...], [0, 1], (0.0, 1.0)),
            (list[float], [1, 2.5], [1.0, 2.5]),
            (dict[float, str], {1: "a"}, {1.0: "a"}),
            (float, {"__cast__": "float", "__value__": 1}, 1.0),
        ],
        ids=["fixed-tuple", "variadic-tuple", "list", "dict-key", "cast"],
    )
    def test_a_float_position_builds_a_float(self, tp: Any, data: Any, expected: Any) -> None:
        """An item, a key and a pinned value are each the ``float`` their token would be."""
        assert repr(construct(tp, data)) == repr(expected)  # the repr tells 1 from 1.0


@dataclass
class _NamedVariant:
    name: str = "field"


@dataclass
class _OtherVariant:
    other: str = "o"


class TestAClassKeyNamingAClassThatRefusesNoArguments:
    """A class key naming an all-default class that refuses ``{}`` is refused as a coercion (BUG-213)."""

    def test_tag_alone_on_a_refusing_class_is_a_coercion(self) -> None:
        """A tag naming an all-default class that refuses {} is refused as a coercion (BUG-213).

        The tag is supplied data, so the field is not missing: the refusal names the class and
        quotes Python's own text, as the auto-bound owner of an instance method already does.
        """
        with pytest.raises(TypeCoercionError, match="with no arguments") as exc_info:
            construct(UUID | int, {"class": "uuid.UUID"})
        msg = str(exc_info.value)
        assert "uuid.UUID" in msg
        assert "one of the hex, bytes, bytes_le, fields, or int arguments must be given" in msg

    def test_tag_beside_the_refusing_classs_fields_builds(self) -> None:
        """The refusal's advice is real: the class's fields beside the tag build it."""
        assert construct(UUID | int, {"class": "uuid.UUID", "int": 5}) == UUID(int=5)


class _BasePt(NamedTuple):
    x: int
    y: int


class TestReplaceBaseIsAList:
    """The ``__base__`` key a patch carries holds the base list, or construction refuses it (BUG-170).

    Only a file can still write the key itself. Its value was read with ``list()``, so an int
    escaped as a raw ``TypeError`` and a string was split into its characters.
    """

    @pytest.mark.parametrize(
        "tp",
        [list[int], tuple[int, int], _BasePt],
        ids=["list", "fixed-tuple", "namedtuple"],
    )
    @pytest.mark.parametrize("base", [5, "12"], ids=["int", "str"])
    def test_base_that_is_no_list_is_refused(self, tp: Any, base: Any) -> None:
        """Neither an int nor a string is a base list, whatever ``list()`` makes of it."""
        with pytest.raises(TypeCoercionError, match=re.escape("at 'v': '__base__' must hold a list")):
            construct(tp, {ListOp.BASE: base, "0": 1}, path=("v",))


class TestListOpOnADict:
    """A list op the merge recorded below a dict is refused, never built as one of its keys (FEAT-3)."""

    def test_list_op_below_a_dict_is_refused(self) -> None:
        """``{__delete__: [1]}`` beside a dict's keys names the op and the field."""
        with pytest.raises(TypeCoercionError, match=re.escape("Cannot apply '__delete__' to the dict at 'd'")):
            construct(dict[str, list[int]], {"a": [1], ListOp.DELETE: [1]}, path=("d",))


class TestListOpOnAFixedArity:
    """An append on a fixed-arity sequence applies over the base it carries, or is refused (BUG-221).

    A fixed tuple and a namedtuple have no length to grow or shrink into, so an append with no
    base below it is refused as the dict field refuses one, naming the op; one carried with
    its base applies, and the result's length is checked as a list's would be. A list delete
    is refused either way: a position is unset in place, by a delete at it (BUG-243).
    """

    def test_a_fixed_tuple_refuses_an_append_with_no_base(self) -> None:
        """The op is named, not read as a key that is no index."""
        msg = "Cannot apply '__append__' to the tuple[int, int] at 't': it is an operation on a list."
        with pytest.raises(TypeCoercionError, match=re.escape(msg)):
            construct(tuple[int, int], {ListOp.APPEND: [0]}, path=("t",))

    def test_a_namedtuple_refuses_an_append_with_no_base(self) -> None:
        """The op is named, not reported as an unknown field."""
        msg = "Cannot apply '__append__' to the namedtuple _BasePt at 'p': it is an operation on a list."
        with pytest.raises(TypeCoercionError, match=re.escape(msg)):
            construct(_BasePt, {ListOp.APPEND: [0]}, path=("p",))

    @pytest.mark.parametrize("op", [ListOp.DELETE, ListOp.DELETE_AFTER], ids=str)
    @pytest.mark.parametrize("base", [{}, {ListOp.BASE: [1, 2]}], ids=["no-base", "carried-base"])
    def test_a_list_delete_is_refused_naming_the_unset(self, op: ListOp, base: dict[Any, Any]) -> None:
        """A delete would shift the positions after it; the message names the delete a position takes."""
        msg = f"Cannot apply {str(op)!r} to the tuple[int, int] at 't': a fixed-length sequence keeps its length"
        with pytest.raises(TypeCoercionError, match=re.escape(msg)):
            construct(tuple[int, int], {**base, op: [0]}, path=("t",))
        with pytest.raises(TypeCoercionError, match=re.escape("{__unset__: true}")):
            construct(_BasePt, {**base, op: [0]}, path=("p",))

    def test_a_delete_at_a_position_unsets_it(self) -> None:
        """A delete at a position leaves it to be filled as an unset one is (BUG-243)."""
        assert construct(tuple[int | None, int], {ListOp.BASE: [1, 2], "0": DICT_DELETE}, path=("t",)) == (None, 2)
        with pytest.raises(MissingFieldError) as ei:
            construct(_BasePt, {ListOp.BASE: [1, 2], "x": DICT_DELETE}, path=("p",))
        assert ei.value._path == ("p", "x")

    def test_an_append_over_a_carried_base_overruns_it(self) -> None:
        """An append past the arity is refused as the list it makes."""
        with pytest.raises(TypeCoercionError, match=re.escape("expected 2 elements, got 3")):
            construct(tuple[int, int], {ListOp.BASE: [1, 2], ListOp.APPEND: [3]}, path=("t",))

    def test_an_append_completing_a_short_base_builds(self) -> None:
        """An append that fills the arity over a carried base builds, as the list it makes."""
        assert construct(tuple[int, int], {ListOp.BASE: [1], ListOp.APPEND: [3]}, path=("t",)) == (1, 3)


class TestIndexKeyedList:
    """An index-keyed list reads an integer key as its string spelling (D6), and a delete needs a base."""

    def test_integer_keys_build_the_list(self) -> None:
        """A YAML mapping ``{0: 9, 1: 8}`` keys its entries by integer."""
        assert construct(list[int], {0: 9, 1: 8}, path=("xs",)) == [9, 8]

    def test_integer_keys_are_checked_for_gaps(self) -> None:
        """The gap is the index no key spells, whichever form the keys take."""
        with pytest.raises(TypeCoercionError, match=re.escape("gap(s) at index/indices [1]")):
            construct(list[int], {0: 9, 2: 7}, path=("xs",))

    def test_an_optional_element_fills_a_gap_with_none(self) -> None:
        """An Optional element type accepts the hole."""
        assert construct(list[int | None], {0: 9, "2": 7}, path=("xs",)) == [9, None, 7]

    def test_a_delete_after_an_append_needs_a_base(self) -> None:
        """``__delete_after__`` alone is refused as a delete with no base, not as a raw ``TypeError``."""
        with pytest.raises(TypeCoercionError, match="requires a base list"):
            construct(list[int], {ListOp.DELETE_AFTER: [0]}, path=("xs",))


class TestAnUnsetFixedTuplePosition:
    """A fixed tuple's position no base and no patch filled is a missing field (D7)."""

    def test_an_unset_position_is_missing(self) -> None:
        """``{1: 5}`` leaves ``t[0]`` unset: the error names it and the flag that sets it."""
        with pytest.raises(MissingFieldError) as ei:
            construct(tuple[int, int], {"1": 5}, path=("t",))
        assert ei.value._path == ("t", 0)
        assert "Missing required field 't[0]' of type int. Set it via CLI (--t.0)" in str(ei.value)

    def test_a_position_past_a_short_base_is_missing(self) -> None:
        """A base shorter than the arity leaves the positions after it unset."""
        with pytest.raises(MissingFieldError) as ei:
            construct(tuple[int, int, int], {ListOp.BASE: [1], "2": 3}, path=("t",))
        assert ei.value._path == ("t", 1)

    def test_an_optional_position_is_none(self) -> None:
        """An Optional position left unset is ``None``, as before."""
        assert construct(tuple[int | None, int], {"1": 5}, path=("t",)) == (None, 5)


@dataclass
class _TupleWithDefault:
    u: tuple[int, int] = (0, 0)


@dataclass
class _TupleWithoutDefault:
    u: tuple[int, int]


class TestPlainSpellingOfAListOpOnASequence:
    """A plain-string list-op key in ``build()`` data is refused from both targets alike (BUG-209).

    The merged dict holds the ops as markers, so the plain spelling is a data key no channel
    can produce. Against a default it was skipped as a stray and the base it spelled never
    entered; without one it was refused as the non-integer patch key it is.
    """

    @pytest.mark.parametrize("key", sorted(MERGE_OP_KEYS))
    def test_every_op_spelling_is_refused_naming_the_key(self, key: str) -> None:
        """Each of the four spellings meets the same refusal, default or not."""
        match = re.escape(f"at 'u': {key!r} spells a list op, which only a configuration file writes")
        with pytest.raises(TypeCoercionError, match=match):
            confarg.build(_TupleWithDefault, {"u": {key: [1, 2], "z": 5}})
        with pytest.raises(TypeCoercionError, match=match):
            confarg.build(_TupleWithoutDefault, {"u": {key: [1, 2], "z": 5}})

    def test_both_targets_refuse_identically(self) -> None:
        """The refusal is one text from the defaulted patch path and the bare path alike."""
        errors = []
        for target in (_TupleWithDefault, _TupleWithoutDefault):
            with pytest.raises(TypeCoercionError) as ei:
                confarg.build(target, {"u": {"__base__": [1, 2], "z": 5}})
            errors.append(str(ei.value))
        assert errors[0] == errors[1]

    def test_a_non_reserved_stray_is_refused_like_a_file_bases(self) -> None:
        """A stray over a default is refused as over a lower file's list: the default is that base (FEAT-37).

        It was tolerated while ``_resolve_tuple_partial`` patched the default in place, the
        skip that dropped BUG-209's plain spelling, BUG-210's pin and BUG-221's marker.
        """
        errors = []
        for target, data in (
            (_TupleWithDefault, {"u": {"0": 9, "z": 5}}),
            (_TupleWithoutDefault, {"u": {ListOp.BASE: [0, 0], "0": 9, "z": 5}}),
        ):
            with pytest.raises(TypeCoercionError, match=re.escape("dict keys must be integer indices")) as ei:
                confarg.build(target, data)
            errors.append(str(ei.value))
        assert errors[0] == errors[1]

    def test_the_marker_spelling_still_carries_the_base(self) -> None:
        """The marker, not the plain string, is the op: it still replaces the default."""
        assert confarg.build(_TupleWithDefault, {"u": {ListOp.BASE: [7, 8]}}).u == (7, 8)


@dataclass
class _ScalarFieldConfig:
    """A scalar field, the ticket's shape: no struct for a tag to select."""

    n: int = 0


@dataclass
class _OtherStruct:
    """A class the scalar field's annotation does not accept."""

    z: int = 3


class TestClassKeyOnAScalarField:
    """A tagged dict on a scalar field is refused naming the tag and a 'call:' spec (BUG-188).

    The tag picks the class to build from the keys beside it; a scalar is built from one value,
    so no class can be picked, and the refusal names the key it refuses and where a value can
    come from instead.
    """

    def test_the_refusal_names_the_tag_and_points_to_call(self) -> None:
        """The repro's dict on an int field names the 'class' key and a 'call:' spec."""
        data = {"class": f"{__name__}._OtherStruct", "z": 1}
        with pytest.raises(TypeCoercionError, match="'class' key picks the class to build") as ei:
            confarg.build(_ScalarFieldConfig, {"n": data})
        assert "'call:' spec computes a value the field's type accepts" in str(ei.value)

    def test_an_optional_scalar_fails_as_its_variant(self) -> None:
        """Optional[int] fails as an int field does: the same refusal, naming int, at the same path."""
        tag = f"{__name__}._OtherStruct"
        with pytest.raises(TypeCoercionError) as exc_info:
            construct(int | None, {"class": tag}, path=("n",))
        assert str(exc_info.value) == _no_class_refusal(
            "int", "int is built from one value, not from keys", tag, path="n"
        )

    def test_an_untagged_dict_keeps_the_generic_refusal(self) -> None:
        """A dict carrying no tag key still fails the leaf's own coercion message."""
        with pytest.raises(TypeCoercionError, match=r"Cannot coerce dict \{'a': 1\} to int at 'n'"):
            construct(int, {"a": 1}, path=("n",))


# ---------------------------------------------------------------------------
# An Any variant is tried last (BUG-117)
# ---------------------------------------------------------------------------


@dataclass
class _AnyPeer:
    a: int = 0


@dataclass
class _AnyBase:
    a: int = 0


@dataclass
class _AnyBaseSub(_AnyBase):
    b: int = 0


class TestUnionWithAny:
    """``Any`` beside other variants takes only what every other variant refused (BUG-117).

    Each union is written in both declaration orders: like the stealing rank, the order a union
    is spelled in does not decide which variant takes a value.
    """

    @pytest.mark.parametrize("tp", [int | Any, Any | int])
    def test_a_token_another_variant_takes_is_not_kept_as_text(self, tp: Any) -> None:
        """'3' is the int; 'abc', which int refuses, is the text, as a plain str."""
        assert construct(tp, _StrToken("3")) == 3
        result = construct(tp, _StrToken("abc"))
        assert result == "abc"
        assert type(result) is str

    @pytest.mark.parametrize("tp", [int | Any | None, Any | int | None])
    def test_a_none_word_selects_none(self, tp: Any) -> None:
        """None ranks among the typed variants, so a none word is None, not the text 'none'."""
        assert construct(tp, _StrToken("none")) is None

    @pytest.mark.parametrize("tp", [Path | Any, Any | Path])
    def test_a_native_value_goes_to_the_typed_variant_first(self, tp: Any) -> None:
        """A file's string is a Path whichever side of the union Any is written on."""
        assert construct(tp, "a") == Path("a")

    @pytest.mark.parametrize("tp", [_AnyPeer | Any, Any | _AnyPeer])
    def test_a_struct_variant_keeps_its_fields(self, tp: Any) -> None:
        """A dict the struct takes builds the struct; one it refuses stays the dict."""
        assert construct(tp, {"a": 1}) == _AnyPeer(a=1)
        assert construct(tp, {"z": 1}) == {"z": 1}

    @pytest.mark.parametrize("tp", [list[int] | Any, Any | list[int]])
    def test_a_lone_cli_token_still_falls_back_to_the_list(self, tp: Any) -> None:
        """The one-element-list fallback of a lone CLI token comes before Any."""
        assert construct(tp, _UnionSeqToken("3")) == [3]

    def test_a_tag_naming_a_variant_still_selects_it(self) -> None:
        """The tag keeps picking the struct variant's subclass it names."""
        data = {"class": f"{__name__}._AnyBaseSub", "a": 1, "b": 2}
        assert construct(_AnyBase | Any, data) == _AnyBaseSub(a=1, b=2)


class TestAUnionWithoutNoneTakesNoNone:
    """A native ``None`` meets a union's variants as any value does (BUG-298).

    Only a union holding ``None`` takes it outright, as ``construct()`` does before any variant
    is asked; any other union took it unasked, so a file's ``null`` loaded into ``int | str``
    where a lone ``str`` field refuses it.
    """

    @pytest.mark.parametrize(
        ("tp", "spelled"),
        [
            pytest.param(int | str, "int | str", id="scalars"),
            pytest.param(_NamedVariant | _OtherVariant, "_NamedVariant | _OtherVariant", id="structs"),
            pytest.param(list[int] | dict[str, int], "list[int] | dict[str, int]", id="collections"),
            pytest.param(Callable[[], Any] | int, "Callable[[], Any] | int", id="callable"),
        ],
    )
    def test_none_is_refused(self, tp: Any, spelled: str) -> None:
        """No variant takes None, so the union refuses it as a lone variant does."""
        with pytest.raises(TypeCoercionError, match=re.escape(f"Cannot coerce NoneType None to {spelled} at 'x'")):
            construct(tp, None, path=("x",))

    @pytest.mark.parametrize("tp", [int | Any, Any | int])
    def test_an_any_variant_takes_none(self, tp: Any) -> None:
        """Any holds every value, None included, as the leaf walk's last rung."""
        assert construct(tp, None) is None

    def test_a_literal_none_variant_takes_none(self) -> None:
        """A Literal holding None is a variant that takes it."""
        assert construct(int | Literal["a", None], None) is None


class TestAnyHoldsNoToken:
    """What an ``Any`` field holds is plain text, never a channel's token."""

    def test_a_token_is_held_as_a_str(self) -> None:
        """A bare Any field built from a token holds a plain str."""
        result = construct(Any, _StrToken("x"))
        assert result == "x"
        assert type(result) is str

    def test_tokens_inside_a_container_are_held_as_str(self) -> None:
        """A CSV-shaped value of tokens, keys included, is held as plain strings."""
        result = construct(Any, [{_StrToken("a"): _StrToken("1")}])
        assert result == [{"a": "1"}]
        ((key, value),) = result[0].items()
        assert type(key) is str
        assert type(value) is str

    def test_a_value_holding_no_token_is_the_same_object(self) -> None:
        """A native value passes through as the very object a caller gave."""
        data = {"a": [1, {"b": "c"}]}
        assert construct(Any, data) is data

    def test_a_list_of_any_holds_str(self) -> None:
        """Each element of a list[Any] built from tokens is a plain str."""
        result = construct(list[Any], [_StrToken("a")])
        assert [type(v) for v in result] == [str]


@dataclass
class _Derived:
    """A field computed after ``__init__``, which ``__init__`` does not take."""

    n: int = 1
    derived: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.derived = self.n * 10


@dataclass
class _Seeded:
    """An ``__init__``-only argument the instance never stores."""

    n: int = 1
    seed: InitVar[int] = 0

    def __post_init__(self, seed: int) -> None:
        self.n += seed


@dataclass
class _SeededRequired:
    """An ``InitVar`` with no default."""

    seed: InitVar[int]
    n: int = 1

    def __post_init__(self, seed: int) -> None:
        self.n += seed


@dataclass(init=False)
class _HandInit:
    """Dataclass fields beside a handwritten ``__init__`` that takes none of them."""

    a: int
    b: int = 2

    def __init__(self, total: int) -> None:
        self.a = total - 2
        self.b = 2


@dataclass(init=False)
class _PositionalOnlyInit:
    """A handwritten ``__init__`` whose parameter takes no keyword."""

    a: int

    def __init__(self, a: int, /) -> None:
        self.a = a


@dataclass
class _Parent:
    n: int = 1


class _UndecoratedChild(_Parent):
    """A dataclass subclass, not decorated itself, with an ``__init__`` of its own."""

    def __init__(self, extra: str = "e", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.extra = extra


class TestAStructsMembersAreItsConstructorsParameters:
    """A dataclass is set through its ``__init__`` parameters, as a plain class is (FEAT-14)."""

    def test_an_init_false_field_is_no_member(self) -> None:
        """A field ``__init__`` does not take is computed, never passed, even from its default."""
        assert construct(_Derived, {"n": 2}) == _Derived(n=2)
        assert construct(_Derived, {}).derived == 10

    def test_an_init_false_field_is_refused_as_unknown(self) -> None:
        """Data naming it is an unknown field, as ``dataclasses.replace()`` refuses it."""
        with pytest.raises(TypeCoercionError, match=r"Unknown field\(s\) \['derived'\] for _Derived"):
            construct(_Derived, {"derived": 5})

    def test_an_init_var_is_a_member(self) -> None:
        """An ``InitVar`` is set as the parameter it is, typed by the type it wraps."""
        assert construct(_Seeded, {"seed": 5}).n == 6

    def test_an_init_var_default_applies(self) -> None:
        """An ``InitVar`` nobody set takes its declared default."""
        assert construct(_Seeded, {}).n == 1

    def test_a_required_init_var_is_a_missing_field(self) -> None:
        """An ``InitVar`` with no default is a required member."""
        with pytest.raises(MissingFieldError, match="'seed'"):
            construct(_SeededRequired, {"n": 2})

    def test_a_handwritten_init_is_read_as_written(self) -> None:
        """The members are the handwritten ``__init__``'s parameters, not the fields it sets."""
        built = construct(_HandInit, {"total": 7})
        assert (built.a, built.b) == (5, 2)
        with pytest.raises(TypeCoercionError, match=r"Unknown field\(s\) \['a'\] for _HandInit"):
            construct(_HandInit, {"a": 1, "total": 7})

    def test_a_handwritten_positional_only_parameter_is_reached(self) -> None:
        """A dataclass is called through the positional split too, so ``a, /`` is filled by position."""
        assert construct(_PositionalOnlyInit, {"a": 3}).a == 3

    def test_an_undecorated_subclass_reads_its_own_init(self) -> None:
        """A subclass's own ``__init__`` decides, ``**kwargs`` included, as for a plain class."""
        built = construct(_UndecoratedChild, {"extra": "x", "kwargs": {"n": 2}})
        assert (built.extra, built.n) == ("x", 2)


class _NoInit:
    """No ``__init__`` and no ``__new__`` of its own."""


class _EmptyInit:
    def __init__(self) -> None:
        self.ready = True


class _NewOnly:
    """Its parameters are ``__new__``'s, since ``__init__`` is ``object``'s."""

    x: int

    def __new__(cls, x: int = 0) -> "_NewOnly":
        obj = super().__new__(cls)
        obj.x = x
        return obj


class _ForwardingNew:
    """A ``__new__`` forwarding everything beside the ``__init__`` that names the parameters."""

    def __new__(cls, *args: Any, **kwargs: Any) -> "_ForwardingNew":
        return super().__new__(cls)

    def __init__(self, x: int = 0) -> None:
        self.x = x


@dataclass
class _HoldsNoInit:
    m: _NoInit


@dataclass
class _HoldsEmptyInit:
    m: _EmptyInit


class TestAClassTakingNothingIsAStructWithNoFields:
    """A constructor that takes no argument makes a struct with no fields, as a field-less dataclass (BUG-153)."""

    @pytest.mark.parametrize("tp", [_NoInit, _EmptyInit])
    def test_it_builds_from_an_empty_dict(self, tp: type) -> None:
        """``{}`` builds it, whether ``__init__`` is inherited from ``object`` or declared empty."""
        assert isinstance(construct(tp, {}), tp)

    @pytest.mark.parametrize("holder", [_HoldsNoInit, _HoldsEmptyInit])
    def test_a_missing_field_builds_it_from_nothing(self, holder: type) -> None:
        """A field holding it builds from nothing, as a defaulted struct does."""
        assert construct(holder, {}).m is not None

    def test_object_init_offers_no_args_or_kwargs(self) -> None:
        """``object.__init__``'s ``*args, **kwargs`` are no fields of a class inheriting it."""
        with pytest.raises(TypeCoercionError, match=r"Unknown field\(s\) \['kwargs'\] for _NoInit"):
            construct(_HoldsNoInit, {"m": {"kwargs": {"x": "1"}}})

    @pytest.mark.parametrize("tp", [_NoInit, _EmptyInit])
    def test_a_class_tag_selects_it(self, tp: type) -> None:
        """A tag naming it builds it, as it builds a field-less dataclass."""
        assert isinstance(construct(tp, {"class": f"{__name__}.{tp.__name__}"}), tp)

    def test_new_is_read_when_init_is_objects(self) -> None:
        """With ``object.__init__``, the call's parameters are ``__new__``'s, typed by its annotations."""
        assert construct(_NewOnly, {"x": 5}).x == 5

    def test_a_forwarding_new_does_not_hide_init(self) -> None:
        """A class defining ``__init__`` is read by it, whatever ``__new__`` takes."""
        assert construct(_ForwardingNew, {"x": 5}).x == 5


class _SeededRandom(random.Random):
    """Holds C storage through ``_random.Random``, and takes nothing."""

    def __init__(self) -> None:
        super().__init__(42)


class _NoArgLocal(threading.local):
    """Holds C storage through ``_thread._local``, and takes nothing."""

    def __init__(self) -> None:
        self.n = 1


class _NoArgError(Exception):
    """Holds C storage through ``BaseException``, and takes nothing."""

    def __init__(self) -> None:
        super().__init__()


class _OneSlot:
    __slots__ = "x"  # noqa: PLC0205  # the string form is the case under test


class _TwoSlots:
    __slots__ = ("a", "b")


class _DictSlot:
    __slots__ = ("__dict__",)


class _SlotBase:
    __slots__ = ("x",)


class _SlotDeclaredAgain(_SlotBase):
    __slots__ = ("x",)


class TestAClassTakingNothingThatHoldsCStorageIsNoStruct:
    """A class taking nothing whose instances hold C storage is an unsupported leaf (BUG-268)."""

    @pytest.mark.parametrize(
        "tp",
        [_thread.LockType, _SeededRandom, _NoArgLocal, _NoArgError],
        ids=["lock", "random-subclass", "thread-local", "exception-subclass"],
    )
    def test_it_is_refused_as_an_unsupported_leaf(self, tp: type) -> None:
        """``{}`` builds nothing: a fresh instance is not the one a dump came from."""
        with pytest.raises(TypeCoercionError, match=rf"Unsupported leaf type {tp.__name__} at"):
            construct(tp, {})

    def test_a_class_tag_naming_the_lock_builds_nothing(self) -> None:
        """``{class: threading.Lock}`` is refused on every version, where ``{call: threading.Lock}`` builds a lock."""
        with pytest.raises(TypeCoercionError):
            construct(Any, {"class": "threading.Lock"})
        assert isinstance(construct(Any, {"call": "threading.Lock"}), _thread.LockType)

    def test_one_taking_parameters_stays_a_struct(self) -> None:
        """A class holding C storage is built from the parameters it takes, as ``random.Random(x)``."""
        built = construct(random.Random, {"class": "random.Random", "x": 1})
        assert built.random() == random.Random(1).random()

    @pytest.mark.parametrize(
        "tp", [_OneSlot, _TwoSlots, _DictSlot, _SlotDeclaredAgain], ids=["str", "tuple", "dict-slot", "declared-again"]
    )
    def test_slots_are_storage_an_attribute_reaches(self, tp: type) -> None:
        """A slot is no C storage, however declared, a base's slot declared again included: ``{}`` builds the class."""
        assert isinstance(construct(tp, {}), tp)

    @pytest.mark.usefixtures("leaf_registry")
    def test_a_registered_class_is_a_leaf(self) -> None:
        """``register_leaf_type`` makes such a class a leaf, built by its coercion."""
        confarg.register_leaf_type(_thread.LockType, lambda _: threading.Lock())
        assert isinstance(construct(_thread.LockType, "fresh"), _thread.LockType)


@dataclass
class _TagA:
    a: int = 0


@dataclass
class _TagB:
    b: int = 0


@dataclass
class _TagHolder:
    union: _TagA | _TagB | None = None
    field: _TagA | None = None
    anything: Any = None
    fn: Callable[..., Any] | None = None


class TestATagThatIsNoStringIsRefused:
    """A ``class:`` tag is a dotted path; any other value is refused as ``call:`` refuses one (BUG-235)."""

    @pytest.mark.parametrize("where", ["union", "field", "anything", "fn"])
    @pytest.mark.parametrize(
        ("tag", "src"),
        [
            pytest.param(3, "int", id="int"),
            pytest.param(1.5, "float", id="float"),
            pytest.param(True, "bool", id="bool"),
            pytest.param(None, "NoneType", id="null"),
            pytest.param(["a"], "list", id="list"),
            pytest.param({"a": 1}, "dict", id="dict"),
            pytest.param(_TagB, "type", id="class-object"),
        ],
    )
    def test_refused_naming_the_tag_and_the_path(self, where: str, tag: Any, src: str) -> None:
        """A union's, a struct field's, an ``Any`` node's and a Callable's tag are refused alike."""
        with pytest.raises(TypeCoercionError, match=rf"^The 'class' key at '{where}' takes a dotted path, got {src}\."):
            construct(_TagHolder, {where: {"class": tag}})

    @pytest.mark.parametrize("where", ["union", "field", "anything", "fn"])
    def test_a_broken_module_stays_an_import_error(
        self,
        where: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest,
    ) -> None:
        """A module that fails while importing is no typo: a ``SymbolImportError`` naming the tag, as for a ``type``."""
        (tmp_path / "bug235_broken.py").write_text("import bug235_missing_dependency\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        request.addfinalizer(lambda: sys.modules.pop("bug235_broken", None))
        with pytest.raises(
            SymbolImportError, match=rf"from the 'class' key at '{where}'.*bug235_missing_dependency"
        ) as e:
            construct(_TagHolder, {where: {"class": "bug235_broken.Thing"}})
        assert not isinstance(e.value, TypeCoercionError)


@dataclass
class _Model:
    x: int = 0


@dataclass
class _SubModel(_Model):
    y: int = 1


@dataclass
class _OtherSubModel(_Model):
    z: int = 2


@dataclass
class _Plain:
    x: int = 0


@dataclass
class _Box[T]:
    item: T


@dataclass
class _Other:
    """Unrelated to ``_Plain``, with the same field names."""

    x: int = 0


@dataclass
class _Instances:
    plain: _Plain | None = None
    model: _Model | None = None
    box: _Box[int] | None = None
    plains: list[_Plain] = field(default_factory=list)
    plain_or_n: _Plain | int = 0
    z: complex | None = None
    lock: _thread.LockType | None = None


class TestABuiltInstanceIsTakenAsItIs:
    """A node takes a value that already is what it names, in a caller's data too (BUG-293).

    A struct node refused every value but a dict, so an instance a caller's ``build()`` data
    held was refused, and a union took it nowhere.
    """

    @pytest.mark.parametrize("api", [confarg.build, confarg.from_dict], ids=["build", "from_dict"])
    def test_a_struct_instance_is_the_same_object(self, api: Callable[..., Any]) -> None:
        """No copy, no revalidation: the instance is the field."""
        plain = _Plain(1)
        assert api(_Instances, {"plain": plain}).plain is plain

    def test_a_subclass_instance_needs_no_tag(self) -> None:
        """A class with subclasses demands a tag of a dict; an instance's class is the tag's answer."""
        sub = _SubModel(4)
        assert confarg.build(_Instances, {"model": sub}).model is sub
        with pytest.raises(TypeCoercionError, match="no 'class' key was provided"):
            confarg.build(_Instances, {"model": {"x": 4}})

    def test_instances_and_dicts_mix_in_a_list(self) -> None:
        """Each item is read at its own position: the instance taken, the dict built."""
        plain = _Plain(1)
        built = confarg.build(_Instances, {"plains": [plain, {"x": 2}]}).plains
        assert built == [_Plain(1), _Plain(2)]
        assert built[0] is plain

    def test_a_generic_structs_members_are_checked(self) -> None:
        """``_Box('s')`` is no ``_Box[int]``: the refusal names the member that does not hold."""
        box = _Box(1)
        assert confarg.build(_Instances, {"box": box}).box is box
        with pytest.raises(TypeCoercionError, match=r"at 'box': it holds 's' at 'box\.item', which is no int"):
            confarg.build(_Instances, {"box": _Box("s")})

    def test_an_unrelated_instance_is_refused_naming_both_classes(self) -> None:
        """Same field names do not make an ``_Other`` a ``_Plain``."""
        refusal = r"got _Other _Other\(x=3\), which is no _Plain; a _Plain, or a dict"
        with pytest.raises(TypeCoercionError, match=refusal):
            confarg.build(_Instances, {"plain": _Other(3)})

    def test_a_value_no_channel_shapes_as_a_struct_is_refused_alike(self) -> None:
        """A file's string is refused by the same message."""
        with pytest.raises(TypeCoercionError, match=r"at 'plain': got str 'abc', which is no _Plain"):
            confarg.build(_Instances, {"plain": "abc"})

    def test_a_union_takes_an_instance_of_its_struct_variant(self) -> None:
        """The variant holding the instance takes it; an unrelated one is refused with the union's message."""
        plain = _Plain(7)
        assert confarg.build(_Instances, {"plain_or_n": plain}).plain_or_n is plain
        with pytest.raises(TypeCoercionError, match=r"Cannot coerce _Other _Other\(x=3\) to _Plain \| int at"):
            confarg.build(_Instances, {"plain_or_n": _Other(3)})

    def test_a_reference_into_an_instance_stays_refused(self) -> None:
        """A reference cannot read inside a built object, so it refuses rather than read a wrong value."""
        with pytest.raises(confarg.exceptions.MissingReferenceError, match="cannot traverse into _Plain"):
            confarg.build(_Instances, {"plain": _Plain(1), "plain_or_n": "${plain.x}"})

    @pytest.mark.parametrize(("name", "value"), [("z", 2j), ("lock", threading.Lock())], ids=["complex", "lock"])
    def test_an_unsupported_leaf_takes_an_instance_of_its_class(self, name: str, value: Any) -> None:
        """The one reading such a leaf has; the dump still refuses to write it."""
        built = confarg.build(_Instances, {name: value})
        assert getattr(built, name) is value
        with pytest.raises(confarg.exceptions.ConfargError, match=f"Cannot serialize .* at '{name}'"):
            confarg.dump(built)

    def test_an_unsupported_leaf_still_reads_no_other_value(self) -> None:
        """Text, or any value of another class, is still refused as the unsupported leaf it is."""
        with pytest.raises(TypeCoercionError, match="Unsupported leaf type complex at 'z'"):
            confarg.build(_Instances, {"z": "2j"})


class _Greeter(Protocol):
    """A Protocol ``isinstance`` cannot ask: it is not runtime-checkable."""

    def greet(self) -> str: ...


class _Greets:
    def greet(self) -> str:
        return "hi"


@dataclass
class _UnderAProtocol:
    greeter: _Greeter | None = None
    greeter_or_n: _Greeter | int = 0


class TestAProtocolIsinstanceCannotAskHoldsNothingYet:
    """Until a Protocol's conformance answers (FEAT-57), one ``isinstance`` cannot ask holds no value (BUG-293).

    Asking ``_holds`` of every value that is no dict raised Python's own ``TypeError`` for a
    file's scalar under such a Protocol, where construction had refused it cleanly.
    """

    def test_a_union_still_reads_its_other_variant(self) -> None:
        """A file's ``5`` is the ``int``."""
        assert confarg.build(_UnderAProtocol, {"greeter_or_n": 5}).greeter_or_n == 5

    @pytest.mark.parametrize("value", ["abc", _Greets()], ids=["text", "instance"])
    def test_a_value_is_refused_cleanly(self, value: Any) -> None:
        """A string or an implementer is refused as no ``_Greeter``, not with ``isinstance``'s ``TypeError``."""
        with pytest.raises(TypeCoercionError, match="which is no _Greeter"):
            confarg.build(_UnderAProtocol, {"greeter": value})

    def test_the_dump_writes_an_implementer_as_foreign(self) -> None:
        """The dump asks the same predicate, so it warns instead of raising."""
        with pytest.warns(ConfargWarning, match="no value of _Greeter"):
            confarg.dump(_UnderAProtocol(greeter=_Greets()))

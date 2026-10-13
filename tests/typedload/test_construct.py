# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for _construct: struct dispatch, union fallbacks and the all-default shortcut."""

import enum
import re
import warnings
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, NamedTuple
from uuid import UUID

import pytest

import confarg
from confarg._merge import (
    MERGE_OP_KEYS,
    ListOp,
)
from confarg._types import _StrToken, _UnionSeqToken
from confarg.exceptions import ConfargWarning, MissingFieldError, TypeCoercionError
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
            _construct_struct_dispatch(_BaseWithSubs, {"x": _StrToken("hello")}, (), "class")

    def test_subclasses_with_tag_constructs(self) -> None:
        """When the union_tag is present, the named subclass is constructed."""
        result = _construct_struct_dispatch(
            _BaseWithSubs,
            {"class": f"{__name__}._Sub1", "x": _StrToken("hello")},
            (),
            "class",
        )
        assert isinstance(result, _Sub1)
        assert result.x == "hello"

    def test_no_subclasses_constructs_directly(self) -> None:
        """When the struct has no subclasses, it is constructed directly without a tag."""
        result = _construct_struct_dispatch(_BaseNoSubs, {}, (), "class")
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

    def test_constructor_refusing_empty_call_is_a_missing_root(self) -> None:
        """The root takes the field's rule: a root that refuses {} is a missing root (BUG-184)."""
        with pytest.raises(MissingFieldError, match="No value provided for target type"):
            confarg.build(UUID, {})

    def test_message_matches_the_scalar_root_message(self) -> None:
        """The message is the one a scalar target nothing supplied gets, naming the target type."""
        with pytest.raises(MissingFieldError) as exc_info:
            confarg.build(UUID, {})
        msg = str(exc_info.value)
        assert repr(UUID) in msg
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


# ---------------------------------------------------------------------------
# A field named exactly like the union tag is a field (BUG-102)
# ---------------------------------------------------------------------------


@dataclass
class _KindPlain:
    Kind: str = "field"


@dataclass
class _KindBase:
    Kind: str = "field"


@dataclass
class _KindSub(_KindBase):
    extra: str = "e"


@dataclass
class _KindVariant:
    Kind: str


@dataclass
class _OtherVariant:
    other: str = "o"


@dataclass
class _KindOnlyBase:
    """Base whose subclass alone owns the tag's spelling (BUG-103)."""


@dataclass
class _KindOnlySub(_KindOnlyBase):
    Kind: str


@dataclass
class _KindOnlyRichBase:
    """Base with its own field beside the subclass-only tag-shaped one."""


@dataclass
class _KindOnlyRichSub(_KindOnlyRichBase):
    host: str

    Kind: str


@dataclass
class _KindOnlyAmbBase:
    """Base whose two subclasses both own the tag's spelling."""


@dataclass
class _KindOnlyAmbA(_KindOnlyAmbBase):
    Kind: str


@dataclass
class _KindOnlyAmbB(_KindOnlyAmbBase):
    Kind: str


@dataclass
class _KindOnlyNeedyBase:
    """Base whose subclass owns the spelling plus a further required field."""


@dataclass
class _KindOnlyNeedySub(_KindOnlyNeedyBase):
    Kind: str
    other: str


@dataclass
class _KindOnlyUnionVariant:
    """Union variant whose subclass alone owns the tag's spelling."""


@dataclass
class _KindOnlyUnionSub(_KindOnlyUnionVariant):
    Kind: str


@dataclass
class _KindOnlyUnionOther:
    other: str = "o"


@dataclass
class _KindLeaf:
    Kind: str = "k"


@dataclass
class _PlainLeaf:
    a: int = 0


@dataclass
class _LeafHolder:
    lf: _KindLeaf


@dataclass
class _PlainLeafHolder:
    lf: _PlainLeaf | None = None


class TestTagFieldCollision:
    """The tag key in data is a real field's value whenever the struct owns the name.

    Construction read the tag before the fields, so a struct with a field named
    exactly like union_tag tried to import the field's value as a class path. The
    field wins instead; the tag is read only where no field bears its name.
    """

    def test_plain_struct_field_wins(self) -> None:
        """A subclass-less struct builds the colliding field from the tag-shaped key."""
        result = _construct_struct_dispatch(_KindPlain, {"Kind": "v"}, (), "Kind")
        assert result == _KindPlain(Kind="v")

    def test_dispatch_struct_field_wins(self) -> None:
        """A base with subclasses still builds from its own colliding field."""
        result = _construct_struct_dispatch(_KindBase, {"Kind": _StrToken("v")}, (), "Kind")
        assert result == _KindBase(Kind="v")

    def test_subclass_only_field_wins(self) -> None:
        """A subclass-only field spelled like the tag is the field, not a class path.

        The shadowing predicate once asked the base's own fields only, so construction
        read the key as the tag and imported the field's value as a class path, stripping
        it from the data — the very field the user had set then went missing (BUG-103).
        """
        result = _construct_struct_dispatch(_KindOnlyBase, {"Kind": _StrToken("v")}, (), "Kind")
        assert result == _KindOnlySub(Kind="v")

    def test_subclass_only_field_value_is_never_a_class_path(self) -> None:
        """A class-path-looking value stays the field's value; nothing is imported."""
        path = f"{__name__}._KindOnlySub"
        result = _construct_struct_dispatch(_KindOnlyBase, {"Kind": _StrToken(path)}, (), "Kind")
        assert result == _KindOnlySub(Kind=path)

    def test_subclass_only_field_with_base_fields(self) -> None:
        """The owning subclass builds from the tag-shaped key beside the base's fields."""
        result = _construct_struct_dispatch(
            _KindOnlyRichBase,
            {"host": "h", "Kind": _StrToken("v")},
            (),
            "Kind",
        )
        assert result == _KindOnlyRichSub(host="h", Kind="v")

    def test_ambiguous_subclass_only_field_raises(self) -> None:
        """Two structurally matching subclasses are a loud ambiguity, not a silent pick."""
        with pytest.raises(TypeCoercionError, match="Ambiguous subclasses"):
            _construct_struct_dispatch(_KindOnlyAmbBase, {"Kind": _StrToken("v")}, (), "Kind")

    def test_subclass_only_field_no_match_raises(self) -> None:
        """A subclass needing more than the tag-shaped key refuses the data loudly."""
        with pytest.raises(TypeCoercionError, match="no subclass accepts"):
            _construct_struct_dispatch(_KindOnlyNeedyBase, {"Kind": _StrToken("v")}, (), "Kind")

    def test_union_variants_subclass_only_field_wins(self) -> None:
        """A union whose variant's subclass owns the colliding field builds that subclass.

        The union's structural fallback tries the variant, and the variant's own
        dispatch selects the subclass structurally — the same fix reached through
        the union route, so no second special case exists to drift.
        """
        result = construct(
            _KindOnlyUnionVariant | _KindOnlyUnionOther,
            {"Kind": _StrToken("v")},
            union_tag="Kind",
        )
        assert result == _KindOnlyUnionSub(Kind="v")

    def test_unshadowed_tag_still_dispatches(self) -> None:
        """A struct without the colliding field keeps importing the tag's class path."""
        result = _construct_struct_dispatch(
            _KindBase,
            {"class": f"{__name__}._KindSub", "extra": "e"},
            (),
            "class",
        )
        assert result == _KindSub(Kind="field", extra="e")

    def test_union_variant_field_wins(self) -> None:
        """A union whose variant owns the colliding field builds that variant structurally."""
        result = construct(_KindVariant | _OtherVariant, {"Kind": "v"}, union_tag="Kind")
        assert result == _KindVariant(Kind="v")

    def test_unshadowed_union_tag_still_dispatches(self) -> None:
        """A union without the colliding field keeps building the named class."""
        result = construct(
            _KindVariant | _OtherVariant,
            {"class": f"{__name__}._KindVariant", "Kind": "v"},
            union_tag="class",
        )
        assert result == _KindVariant(Kind="v")

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

    def test_taggable_leaf_param_shadows_tag(
        self,
        leaf_registry: None,
    ) -> None:
        """A registered leaf whose parameter shadows the tag stays closed.

        The tag is the only thing that opts a leaf back into field construction, so
        a parameter consuming its spelling leaves nothing that can open the leaf.
        """
        confarg.register_leaf_type(_KindLeaf, lambda v: _KindLeaf(str(v)))
        with pytest.raises(TypeCoercionError, match="consumes the tag's spelling"):
            construct(_LeafHolder, {"lf": {"Kind": "v"}}, union_tag="Kind")

    def test_taggable_leaf_without_shadow_still_opens(
        self,
        leaf_registry: None,
    ) -> None:
        """A registered leaf without the colliding parameter keeps opening by tag."""
        confarg.register_leaf_type(_PlainLeaf, lambda v: _PlainLeaf(int(v)))
        result = construct(
            _PlainLeafHolder,
            {"lf": {"Kind": f"{__name__}._PlainLeaf", "a": 5}},
            union_tag="Kind",
        )
        assert result == _PlainLeafHolder(lf=_PlainLeaf(a=5))


class TestShadowedTagWarning:
    """A shadowed tag-shaped key warns on use, at positions where the tag could have dispatched.

    The collision is accepted silently in the architecture note's trade-off only for
    positions that never could dispatch; where a class-path tag was a real alternative,
    ``build()`` emits a ``ConfargWarning`` naming the field path and the remedy, so the
    structural selection the member's value forces is never a surprise.
    """

    def test_subclass_only_field_use_warns(self) -> None:
        """The BUG-103 shape: setting the field warns that no class-path tag dispatches."""
        with pytest.warns(ConfargWarning, match="selected structurally"):
            result = _construct_struct_dispatch(_KindOnlyBase, {"Kind": _StrToken("v")}, (), "Kind")
        assert result == _KindOnlySub(Kind="v")

    def test_base_field_use_on_dispatch_struct_warns(self) -> None:
        """The BUG-102 shape: the base's own field warns where subclasses could dispatch."""
        with pytest.warns(ConfargWarning, match="Rename the field"):
            result = _construct_struct_dispatch(_KindBase, {"Kind": _StrToken("v")}, (), "Kind")
        assert result == _KindBase(Kind="v")

    def test_plain_struct_use_does_not_warn(self) -> None:
        """A struct without subclasses never dispatches, so its own field needs no apology."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _construct_struct_dispatch(_KindPlain, {"Kind": _StrToken("v")}, (), "Kind")
        assert result == _KindPlain(Kind="v")
        assert not any(issubclass(w.category, ConfargWarning) for w in caught)

    def test_unshadowed_tag_dispatch_does_not_warn(self) -> None:
        """A tag that still dispatches by class path is the intended route, not a collision."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _construct_struct_dispatch(
                _KindBase,
                {"class": f"{__name__}._KindSub", "extra": "e"},
                (),
                "class",
            )
        assert result == _KindSub(Kind="field", extra="e")
        assert not any(issubclass(w.category, ConfargWarning) for w in caught)

    def test_union_variant_field_use_warns(self) -> None:
        """A union whose variant owns the spelling warns: the variant is chosen structurally."""
        with pytest.warns(ConfargWarning, match="no class-path tag can dispatch"):
            result = construct(_KindVariant | _OtherVariant, {"Kind": _StrToken("v")}, union_tag="Kind")
        assert result == _KindVariant(Kind="v")

    def test_union_unshadowed_tag_dispatch_does_not_warn(self) -> None:
        """A union tag that still names its class is the intended route."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = construct(
                _KindVariant | _OtherVariant,
                {"class": f"{__name__}._KindVariant", "Kind": _StrToken("v")},
                union_tag="class",
            )
        assert result == _KindVariant(Kind="v")
        assert not any(issubclass(w.category, ConfargWarning) for w in caught)

    def test_union_variants_subclass_only_field_use_warns(self) -> None:
        """The union route through a variant's subclass warns at the union position."""
        with pytest.warns(ConfargWarning, match="selected structurally"):
            result = construct(
                _KindOnlyUnionVariant | _KindOnlyUnionOther,
                {"Kind": _StrToken("v")},
                union_tag="Kind",
            )
        assert result == _KindOnlyUnionSub(Kind="v")


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


_OPS = [ListOp.APPEND, ListOp.DELETE, ListOp.DELETE_AFTER]


class TestListOpOnAFixedArity:
    """A list op on a fixed-arity sequence applies over the base it carries, or is refused (BUG-221).

    A fixed tuple and a namedtuple have no length to grow or shrink into, so an op with no
    base below it is refused as the dict field refuses one, naming the op; one carried with
    its base applies, and the result's length is checked as a list's would be.
    """

    @pytest.mark.parametrize("op", _OPS, ids=str)
    def test_a_fixed_tuple_refuses_an_op_with_no_base(self, op: ListOp) -> None:
        """The op is named, not read as a key that is no index."""
        msg = f"Cannot apply {str(op)!r} to the tuple[int, int] at 't': it is an operation on a list."
        with pytest.raises(TypeCoercionError, match=re.escape(msg)):
            construct(tuple[int, int], {op: [0]}, path=("t",))

    @pytest.mark.parametrize("op", _OPS, ids=str)
    def test_a_namedtuple_refuses_an_op_with_no_base(self, op: ListOp) -> None:
        """The op is named, not reported as an unknown field."""
        msg = f"Cannot apply {str(op)!r} to the namedtuple _BasePt at 'p': it is an operation on a list."
        with pytest.raises(TypeCoercionError, match=re.escape(msg)):
            construct(_BasePt, {op: [0]}, path=("p",))

    def test_a_delete_over_a_carried_base_shortens_it(self) -> None:
        """``--t 1 2 --t.0-`` leaves one element for two positions: the arity refusal, not a key one."""
        with pytest.raises(TypeCoercionError, match=re.escape("expected 2 elements, got 1")):
            construct(tuple[int, int], {ListOp.BASE: [1, 2], ListOp.DELETE: [0]}, path=("t",))

    def test_an_append_over_a_carried_base_overruns_it(self) -> None:
        """An append past the arity is refused as the list it makes."""
        with pytest.raises(TypeCoercionError, match=re.escape("expected 2 elements, got 3")):
            construct(tuple[int, int], {ListOp.BASE: [1, 2], ListOp.APPEND: [3]}, path=("t",))

    def test_ops_over_a_carried_base_build_when_the_arity_holds(self) -> None:
        """A delete after an append keeps two elements, which a fixed tuple builds."""
        data = {ListOp.BASE: [1, 2], ListOp.APPEND: [3], ListOp.DELETE_AFTER: [0]}
        assert construct(tuple[int, int], data, path=("t",)) == (2, 3)

    def test_a_namedtuple_shortened_by_a_delete_misses_its_field(self) -> None:
        """The positions left fill the first fields; the last one is missing."""
        with pytest.raises(MissingFieldError) as ei:
            construct(_BasePt, {ListOp.BASE: [1, 2], ListOp.DELETE: [0]}, path=("p",))
        assert ei.value._path == ("p", "y")


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
        assert "Missing required field 't[0]' of type <class 'int'>. Set it via CLI (--t.0)" in str(ei.value)

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

    The tag selects a subclass of a struct-typed field's annotation; a scalar is no struct,
    so no class can be selected, and the refusal names the key it refuses and where a value
    can come from instead.
    """

    def test_the_refusal_names_the_tag_and_points_to_call(self) -> None:
        """The repro's dict on an int field names the 'class' key and a 'call:' spec."""
        data = {"class": f"{__name__}._OtherStruct", "z": 1}
        with pytest.raises(TypeCoercionError, match="'class' key is the union tag") as ei:
            confarg.build(_ScalarFieldConfig, {"n": data})
        assert "'call:' spec computes a value the field's type accepts" in str(ei.value)

    def test_the_refusal_spells_the_union_tag_it_was_given(self) -> None:
        """A custom tag spelling is named as the key, not the default 'class'."""
        with pytest.raises(TypeCoercionError, match="'Kind' key is the union tag"):
            construct(int, {"Kind": f"{__name__}._OtherStruct"}, path=("n",), union_tag="Kind")

    def test_an_optional_scalar_fails_as_its_variant(self) -> None:
        """Optional[int] fails as an int field does: the same refusal, same path."""
        with pytest.raises(TypeCoercionError, match="'class' key is the union tag"):
            construct(int | None, {"class": f"{__name__}._OtherStruct"}, path=("n",))

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

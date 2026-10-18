# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for register_leaf_type and the _LEAF_COERCIONS extension mechanism."""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple, NewType
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

import confarg
from confarg._types import _StrToken
from confarg.exceptions import ConfargWarning, MissingFieldError, TypeCoercionError
from confarg.typedload._coerce import (
    _LEAF_COERCIONS,
    _LEAF_SERIALIZERS,
    _coerce_leaf,
    _coerce_timezone,
    _format_duration,
    _format_offset,
    _parse_duration,
    _registered_leaf_of,
    _try_coerce,
    _type_kind,
    _TypeKind,
    read_as_object,
)
from confarg.typedload._construct import construct
from tests.conftest import Release

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_registry(leaf_registry: None) -> None:
    """Restore both leaf registries after each test that registers a type or unregisters UUID."""


@pytest.fixture
def _unregistered_uuid() -> None:
    """Take the built-in UUID out of both registries, put back by ``_cleanup_registry``."""
    del _LEAF_COERCIONS[UUID]
    del _LEAF_SERIALIZERS[UUID]


class _Color(Enum):
    RED = "r"


class _Pt(NamedTuple):
    a: int = 0


_UserId = NewType("_UserId", int)


class _Flags(dict):
    """A dict subclass registered as a leaf, read from and written as comma-separated names."""


def _parse_flags(text: Any) -> _Flags:
    return _Flags(dict.fromkeys(str(text).split(","), True))


@dataclass
class _WithFlags:
    f: _Flags


class _Ticket:
    """A class no registry names, registered by the tests of the registration API itself."""

    def __init__(self, text: str) -> None:
        self.text = text


# ---------------------------------------------------------------------------
# TestRegisterLeafType — public API
# ---------------------------------------------------------------------------


class TestRegisterLeafType:
    """Tests for the confarg.register_leaf_type() public API."""

    def test_register_adds_to_leaf_coercions(self) -> None:
        """register_leaf_type adds the type to _LEAF_COERCIONS."""
        confarg.register_leaf_type(_Ticket, _Ticket)
        assert _Ticket in _LEAF_COERCIONS

    def test_register_callable_is_stored(self) -> None:
        """The coerce callable passed to register_leaf_type is stored verbatim."""
        coerce = lambda v: _Ticket(str(v))  # noqa: E731
        confarg.register_leaf_type(_Ticket, coerce)
        assert _LEAF_COERCIONS[_Ticket] is coerce

    def test_register_overrides_previous(self) -> None:
        """Re-registering the same type replaces the previous callable."""
        confarg.register_leaf_type(_Ticket, _Ticket)
        coerce2 = lambda v: _Ticket(str(v))  # noqa: E731
        confarg.register_leaf_type(_Ticket, coerce2)
        assert _LEAF_COERCIONS[_Ticket] is coerce2

    def test_register_stores_the_serializer(self) -> None:
        """The serialize callable passed to register_leaf_type is stored verbatim."""
        serialize = lambda v: v.text  # noqa: E731
        confarg.register_leaf_type(_Ticket, _Ticket, serialize=serialize)
        assert _LEAF_SERIALIZERS[_Ticket] is serialize

    def test_serializer_defaults_to_str(self) -> None:
        """Omitting serialize= registers str, the wire form of most leaf types."""
        confarg.register_leaf_type(_Ticket, _Ticket)
        assert _LEAF_SERIALIZERS[_Ticket] is str

    @pytest.mark.parametrize(
        ("key", "reason"),
        [
            pytest.param(_UserId, "_UserId is a NewType, which confarg reads as int", id="newtype"),
            pytest.param(tuple[int, int], "tuple[int, int] is no class", id="generic-alias"),
            pytest.param(int | str, "int | str is no class", id="union"),
            pytest.param(Annotated[int, "m"], "is no class", id="annotated"),
            pytest.param(Literal["a", "b"], "is no class", id="literal"),
            pytest.param(int, "confarg reads int itself", id="int"),
            pytest.param(str, "confarg reads str itself", id="str"),
            pytest.param(bool, "confarg reads bool itself", id="bool"),
            pytest.param(type(None), "confarg reads NoneType itself", id="none"),
            pytest.param(Any, "confarg reads Any itself", id="any"),
            pytest.param(object, "every value is an object", id="object"),
            pytest.param(type, "confarg reads type itself", id="type"),
            pytest.param(list, "confarg reads list as a list", id="list"),
            pytest.param(dict, "confarg reads dict as a dict", id="dict"),
            pytest.param(tuple, "confarg reads tuple as a tuple", id="tuple"),
            pytest.param(_Color, "confarg reads _Color itself", id="enum"),
            pytest.param(_Pt, "confarg reads _Pt as a namedtuple", id="namedtuple"),
            pytest.param(Callable, "confarg reads Callable as a callable", id="callable"),
        ],
    )
    def test_a_key_no_registration_reaches_is_refused(self, key: Any, reason: str) -> None:
        """Every key whose coercion would never run is refused, naming how confarg reads it instead."""
        with pytest.raises(TypeError, match=re.escape(reason)):
            confarg.register_leaf_type(key, lambda v: v)
        assert key not in _LEAF_COERCIONS

    def test_the_refusal_names_the_key_as_written(self) -> None:
        """A class is named by its name, anything else as Python writes it."""
        with pytest.raises(TypeError, match=re.escape("register_leaf_type(int): confarg reads int itself")):
            confarg.register_leaf_type(int, int)
        with pytest.raises(
            TypeError, match=re.escape("register_leaf_type(tuple[int, int]): tuple[int, int] is no class")
        ):
            confarg.register_leaf_type(tuple[int, int], tuple)

    @pytest.mark.parametrize("key", [complex, _Ticket, Path, Decimal, datetime])
    def test_a_key_construction_reaches_is_accepted(self, key: type) -> None:
        """An unsupported class, a plain class, and a built-in leaf being replaced all register."""
        confarg.register_leaf_type(key, lambda v: v)
        assert key in _LEAF_COERCIONS

    def test_a_builtin_subclass_registration_wins(self) -> None:
        """A registered dict subclass is a leaf both ways, read through its coercion rather than as a dict."""
        confarg.register_leaf_type(_Flags, _parse_flags, serialize=",".join)
        built = confarg.build(_WithFlags, {"f": "a,b"})
        assert built.f == {"a": True, "b": True}
        assert type(built.f) is _Flags
        assert confarg.dump(built) == {"f": "a,b"}

    def test_register_overrides_both_halves(self) -> None:
        """Re-registering the same type replaces the coercion and the serializer together."""
        confarg.register_leaf_type(_Ticket, _Ticket, serialize=lambda v: v.text)
        coerce2 = lambda v: _Ticket(str(v))  # noqa: E731
        confarg.register_leaf_type(_Ticket, coerce2)
        assert _LEAF_COERCIONS[_Ticket] is coerce2
        assert _LEAF_SERIALIZERS[_Ticket] is str


# ---------------------------------------------------------------------------
# TestCoerceLeafCustomType — _coerce_leaf with registered type
# ---------------------------------------------------------------------------

_UUID_STR = "12345678-1234-5678-1234-567812345678"
_UUID_OBJ = UUID(_UUID_STR)


class TestCoerceLeafCustomType:
    """Tests for _coerce_leaf() with registered custom types."""

    def test_coerce_from_str_token(self) -> None:
        """Custom type is coerced from a _StrToken (simulating CLI/env input)."""
        token = _StrToken(_UUID_STR)
        result = _coerce_leaf(UUID, token)
        assert result == _UUID_OBJ
        assert isinstance(result, UUID)

    def test_coerce_from_native_object(self) -> None:
        """Custom type is passed through when already an instance (file input)."""
        result = _coerce_leaf(UUID, _UUID_OBJ)
        assert result == _UUID_OBJ

    def test_coerce_invalid_raises(self) -> None:
        """Invalid input raises TypeCoercionError."""
        token = _StrToken("not-a-uuid")
        with pytest.raises(TypeCoercionError):
            _coerce_leaf(UUID, token)

    @pytest.mark.usefixtures("_unregistered_uuid")
    def test_unregistered_type_raises(self) -> None:
        """A type that is not registered as a leaf raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="Unsupported leaf type"):
            _coerce_leaf(UUID, _StrToken(_UUID_STR))


class TestCoerceLeafAny:
    """_coerce_leaf passes a value through to Any, the leaf every value holds (BUG-212)."""

    def test_native_value_passes_through(self) -> None:
        """A native value is returned as-is."""
        assert _coerce_leaf(Any, 1) == 1
        assert _coerce_leaf(Any, None) is None

    def test_token_passes_through_as_its_text(self) -> None:
        """A string token is returned as the plain str it spells, as construct()'s ANY branch does."""
        result = _coerce_leaf(Any, _StrToken("x"))
        assert result == "x"
        assert type(result) is str


# ---------------------------------------------------------------------------
# TestTryCoerceCustomType — eager coercion during merge
# ---------------------------------------------------------------------------


class TestTryCoerceCustomType:
    """Tests for _try_coerce() with registered custom leaf types."""

    def test_registered_type_is_left_as_written(self) -> None:
        """A registered type's value is an object no file holds, so its token stays as written (BUG-246)."""
        token = _StrToken(_UUID_STR)
        assert _try_coerce(UUID, token, "--value") is token

    @pytest.mark.usefixtures("_unregistered_uuid")
    def test_unregistered_type_returns_token(self) -> None:
        """Unregistered types are not eagerly coerced — token passes through unchanged."""
        token = _StrToken(_UUID_STR)
        result = _try_coerce(UUID, token, "--value")
        assert result is token

    def test_registered_type_is_read_as_its_object(self) -> None:
        """An expression reads it as the object, an optional included, whatever the spelling (BUG-246)."""
        assert read_as_object(UUID | None, _UUID_STR) == _UUID_OBJ
        assert read_as_object(UUID | str, _UUID_STR) == _UUID_STR

    def test_invalid_registered_returns_token(self) -> None:
        """When coercion fails, _try_coerce returns the original token unchanged."""
        token = _StrToken("not-a-uuid")
        result = _try_coerce(UUID, token, "--value")
        assert result is token


# ---------------------------------------------------------------------------
# TestConstructCustomType — construct() integration
# ---------------------------------------------------------------------------


class TestConstructCustomType:
    """Tests for construct() dispatching registered types to _coerce_leaf."""

    def test_construct_from_str_token(self) -> None:
        """construct() coerces a _StrToken to the registered type."""
        result = construct(UUID, _StrToken(_UUID_STR))
        assert result == _UUID_OBJ

    def test_construct_optional_from_str_token(self) -> None:
        """construct() coerces a _StrToken through an Optional[registered] union."""
        result = construct(UUID | None, _StrToken(_UUID_STR))
        assert result == _UUID_OBJ

    def test_construct_optional_none(self) -> None:
        """construct() returns None for an Optional[registered] field when data is None."""
        result = construct(UUID | None, None)
        assert result is None


# ---------------------------------------------------------------------------
# TestRegisteredLeafInStructUnion — a registered leaf is not a struct variant
# ---------------------------------------------------------------------------


class TestRegisteredLeafInStructUnion:
    """A registered leaf never competes with structs for structural matching.

    ``UUID`` is a struct by introspection — every ``__init__`` parameter has a
    default — so a ``Release | UUID`` field used to see two struct variants and
    refuse to pick one, even though only ``Release`` is really a struct.
    """

    def test_struct_variant_wins_an_untagged_dict(self) -> None:
        """A dict matching the struct constructs it, with no class tag needed."""
        assert construct(Release | UUID, {"version": 2}) == Release(version=2)

    def test_leaf_variant_still_wins_a_scalar(self) -> None:
        """The registered leaf still claims the scalar form of the same union."""
        assert construct(Release | UUID, _StrToken(_UUID_STR)) == _UUID_OBJ


# ---------------------------------------------------------------------------
# TestTaggedRegisteredLeaf — an explicit class tag opts a leaf back into fields
# ---------------------------------------------------------------------------


@dataclass
class _Tagged:
    id: UUID


@dataclass
class _TaggedUnion:
    id: Release | UUID


_UUID_TAG = {"class": "uuid.UUID", "int": 5}
_UUID_FROM_TAG = UUID(int=5)


class TestTaggedRegisteredLeaf:
    """Registering a type as a leaf must not break configurations that tag it.

    ``{"class": "uuid.UUID", ...}`` builds a ``UUID`` from its ``__init__``
    parameters before registration, and registration may not take that spelling
    away — an explicit tag is the one thing that opts a registered leaf back into
    field construction.
    """

    def test_tag_builds_a_leaf_typed_field_from_fields(self) -> None:
        """A tagged dict builds the registered leaf of a plainly-typed field."""
        assert confarg.build(_Tagged, {"id": dict(_UUID_TAG)}) == _Tagged(id=_UUID_FROM_TAG)

    def test_tag_builds_a_leaf_variant_of_a_union(self) -> None:
        """A tagged dict names the registered leaf variant of a union and builds it."""
        assert confarg.build(_TaggedUnion, {"id": dict(_UUID_TAG)}) == _TaggedUnion(id=_UUID_FROM_TAG)

    def test_tag_builds_the_same_value_after_registration_as_before(self) -> None:
        """Registration leaves the tagged spelling exactly where it was before it."""
        registered = confarg.build(_Tagged, {"id": dict(_UUID_TAG)})
        del _LEAF_COERCIONS[UUID], _LEAF_SERIALIZERS[UUID]
        assert confarg.build(_Tagged, {"id": dict(_UUID_TAG)}) == registered

    def test_custom_union_tag_is_honoured(self) -> None:
        """The opt-in follows union_tag=, not a hard-coded 'class' key."""
        data = {"id": {"kind": "uuid.UUID", "int": 5}}
        assert confarg.build(_Tagged, data, union_tag="kind") == _Tagged(id=_UUID_FROM_TAG)

    def test_untagged_dict_is_not_taken_apart(self) -> None:
        """Without a tag the leaf stays opaque — and the error says how to ask for fields."""
        with pytest.raises(TypeCoercionError, match="'class'"):
            confarg.build(_Tagged, {"id": {"int": 5}})

    def test_tag_naming_an_unrelated_class_is_rejected(self) -> None:
        """A tag that does not name the leaf (or a subclass of it) is still an error."""
        with pytest.raises(TypeCoercionError, match="not a subclass"):
            confarg.build(_Tagged, {"id": {"class": "tests.conftest.Release"}})


# ---------------------------------------------------------------------------
# TestRegisteredLeafIsNotAutoBuilt — no implicit path reaches a leaf's fields
# ---------------------------------------------------------------------------


@dataclass
class _Ident:
    id: UUID
    n: int


@dataclass
class _Serial:
    id: int
    n: int


class TestRegisteredLeafIsNotAutoBuilt:
    """No implicit path takes a registered leaf apart, however struct-like it looks."""

    def test_missing_leaf_field_raises_missing_field(self) -> None:
        """A missing required leaf field is a MissingFieldError, not a stdlib TypeError.

        Every ``UUID.__init__`` parameter has a default, so the "struct with
        all-default fields is built from {}" shortcut used to call ``UUID()`` and
        let its own ``TypeError`` escape ``build()``.
        """
        with pytest.raises(MissingFieldError, match="id"):
            confarg.build(_Tagged, {})

    def test_leaf_typed_field_disambiguates_a_struct_union(self) -> None:
        """A value the leaf accepts picks the variant that holds it.

        Structural refinement asked whether the value was a valid *dict* for
        ``UUID``'s fields; a UUID string is not, so the variant lost a comparison
        it should have won and the union came out ambiguous.
        """
        assert construct(_Ident | _Serial, {"id": _StrToken(_UUID_STR), "n": 1}) == _Ident(id=_UUID_OBJ, n=1)


# ---------------------------------------------------------------------------
# TestBuildEndToEnd — confarg.build() with a registered leaf type
# ---------------------------------------------------------------------------


@dataclass
class _Config:
    id: UUID
    token: UUID | None = None


class TestBuildEndToEnd:
    """End-to-end tests: confarg.build() with a registered leaf type in a dataclass."""

    def test_build_from_str_token(self) -> None:
        """End-to-end: confarg.build() constructs a dataclass with a registered leaf field."""
        result = confarg.build(_Config, {"id": _StrToken(_UUID_STR)})
        assert result == _Config(id=_UUID_OBJ, token=None)

    def test_build_from_native_uuid(self) -> None:
        """End-to-end: confarg.build() passes through a natively-parsed UUID (from file)."""
        result = confarg.build(_Config, {"id": _UUID_OBJ})
        assert result == _Config(id=_UUID_OBJ, token=None)

    def test_build_optional_field(self) -> None:
        """build() handles an Optional registered field with a _StrToken value."""
        result = confarg.build(
            _Config,
            {"id": _StrToken(_UUID_STR), "token": _StrToken(_UUID_STR)},
        )
        assert result == _Config(id=_UUID_OBJ, token=_UUID_OBJ)


# ---------------------------------------------------------------------------
# TestIntCoercion — _coerce_leaf for int with alternate bases
# ---------------------------------------------------------------------------


class TestIntCoercion:
    """Tests for int coercion: hex, octal, binary, and leading-zero rejection."""

    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("42", 42),
            ("-7", -7),
            ("0", 0),
            ("0x1F", 31),
            ("0X1F", 31),
            ("-0x1F", -31),
            ("0o17", 15),
            ("0O17", 15),
            ("0b1010", 10),
            ("0B1010", 10),
        ],
        ids=[
            "decimal",
            "negative",
            "zero",
            "hex-lower",
            "hex-upper",
            "hex-negative",
            "octal-lower",
            "octal-upper",
            "binary-lower",
            "binary-upper",
        ],
    )
    def test_valid(self, token: str, expected: int) -> None:
        """Valid integer tokens (decimal, hex, octal, binary) are coerced correctly."""
        assert _coerce_leaf(int, _StrToken(token)) == expected

    @pytest.mark.parametrize(
        "token",
        ["042", "-042"],
        ids=["leading-zero-positive", "leading-zero-negative"],
    )
    def test_leading_zero_raises(self, token: str) -> None:
        """Non-zero decimal integers with a leading zero raise TypeCoercionError."""
        with pytest.raises(TypeCoercionError):
            _coerce_leaf(int, _StrToken(token))


# ---------------------------------------------------------------------------
# TestFloatCoercion — a native int, and a finite spelling that overflows
# ---------------------------------------------------------------------------


class TestFloatCoercion:
    """A float reads a file's int as its digits read on the CLI, and warns of a finite overflow (BUG-154)."""

    @pytest.mark.parametrize("value", [1, -7, 0, 2**53 + 1], ids=["one", "negative", "zero", "past-2**53"])
    def test_a_native_int_reads_as_its_text_does(self, value: int) -> None:
        """A file's ``1`` is the ``1.0`` the token ``1`` is, rounded the same way past 2**53."""
        coerced = _coerce_leaf(float, value)
        assert type(coerced) is float
        assert coerced == _coerce_leaf(float, _StrToken(str(value)))

    @pytest.mark.parametrize("value", [True, False])
    def test_a_bool_is_refused(self, value: Any) -> None:
        """A bool is never a number, though ``bool`` subclasses ``int``."""
        with pytest.raises(TypeCoercionError, match="Cannot coerce bool"):
            _coerce_leaf(float, value)

    def test_a_native_float_is_refused_for_an_int(self) -> None:
        """The numeric tower runs one way: a file's ``1.0`` is no ``int``."""
        with pytest.raises(TypeCoercionError, match=r"Cannot coerce float 1\.0 to int"):
            _coerce_leaf(int, 1.0)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (10**400, float("inf")),
            (-(10**400), float("-inf")),
            (_StrToken("1" + "0" * 400), float("inf")),
            (_StrToken("1e400"), float("inf")),
            (_StrToken("-1e400"), float("-inf")),
        ],
        ids=["native-int", "native-negative-int", "token-digits", "token-exponent", "token-negative-exponent"],
    )
    def test_an_overflow_reads_as_inf_and_warns(self, value: Any, expected: float) -> None:
        """A finite spelling too large for a float is the infinity of its sign, named with its path."""
        with pytest.warns(confarg.exceptions.FloatOverflowWarning, match="too large for a float.* at 'f'"):
            assert _coerce_leaf(float, value, "f") == expected

    @pytest.mark.parametrize("value", [_StrToken("inf"), _StrToken("-Infinity"), _StrToken(" INF "), float("inf")])
    def test_an_infinity_spelled_as_such_does_not_warn(self, value: Any) -> None:
        """An infinity word, or the infinity a parser already made, was meant."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert math.isinf(_coerce_leaf(float, value))

    def test_an_eager_token_reads_as_inf_and_warns_naming_its_spelling(self) -> None:
        """A parser holds the infinity in the merged dict, and names the flag the user typed."""
        with pytest.warns(confarg.exceptions.FloatOverflowWarning, match="^1e400 for --f is too large"):
            assert _try_coerce(float, _StrToken(" 1e400"), "--f") == float("inf")

    def test_the_overflow_warning_is_a_confarg_warning(self) -> None:
        """It can be cancelled alone by its category, and a filter on ``ConfargWarning`` still catches it."""
        assert issubclass(confarg.exceptions.FloatOverflowWarning, ConfargWarning)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            warnings.filterwarnings("ignore", category=confarg.exceptions.FloatOverflowWarning)
            assert _coerce_leaf(float, 10**400) == float("inf")

    def test_an_expression_reads_a_native_int_as_the_float_it_builds(self) -> None:
        """A reference reads the built value: a file's ``1`` at a ``float`` field reads ``1.0``."""
        read = read_as_object(float, 1)
        assert type(read) is float
        assert read == 1.0


# ---------------------------------------------------------------------------
# TestNoneTypeCoercion — _coerce_leaf and _try_coerce for NoneType
# ---------------------------------------------------------------------------


class TestNoneTypeCoercion:
    """Tests for NoneType coercion: only None and recognised null tokens are accepted."""

    def test_none_passthrough(self) -> None:
        """A Python None value passes through unchanged."""
        assert _coerce_leaf(type(None), None) is None

    def test_none_token(self) -> None:
        """The string token 'none' is accepted as a valid null representation."""
        assert _coerce_leaf(type(None), _StrToken("none")) is None

    def test_null_token(self) -> None:
        """The string token 'null' is accepted as a valid null representation."""
        assert _coerce_leaf(type(None), _StrToken("null")) is None

    def test_case_insensitive(self) -> None:
        """Null token matching is case-insensitive."""
        assert _coerce_leaf(type(None), _StrToken("NONE")) is None
        assert _coerce_leaf(type(None), _StrToken("NULL")) is None
        assert _coerce_leaf(type(None), _StrToken("Null")) is None

    def test_arbitrary_string_raises(self) -> None:
        """An unrecognised string raises TypeCoercionError instead of silently returning None."""
        with pytest.raises(TypeCoercionError):
            _coerce_leaf(type(None), _StrToken("x"))

    def test_empty_string_accepted(self) -> None:
        """An empty string token (e.g. NOTHING= env var) is accepted as None."""
        assert _coerce_leaf(type(None), _StrToken("")) is None

    def test_try_coerce_none_token(self) -> None:
        """_try_coerce eagerly converts 'none' tokens for NoneType fields."""
        result = _try_coerce(type(None), _StrToken("none"), "--value")
        assert result is None

    def test_try_coerce_invalid_returns_token(self) -> None:
        """_try_coerce returns the token unchanged when coercion would fail."""
        token = _StrToken("x")
        result = _try_coerce(type(None), token, "--value")
        assert result is token

    def test_load_integration_none_token(self) -> None:
        """confarg.load() accepts 'none' for a value: None field."""

        @dataclass
        class Config:
            value: None

        result = confarg.load(Config, argv=["--value", "none"], env={})
        assert result == Config(value=None)

    def test_load_integration_rejects_arbitrary(self) -> None:
        """confarg.load() rejects arbitrary strings for a value: None field."""

        @dataclass
        class Config:
            value: None

        with pytest.raises(TypeCoercionError):
            confarg.load(Config, argv=["--value", "x"], env={})


# ---------------------------------------------------------------------------
# TestTypeKind — the one order every shape dispatch asks in
# ---------------------------------------------------------------------------


class _Point(NamedTuple):
    x: int
    y: int


type _Alias = list[int]


class TestTypeKind:
    """_type_kind names one shape per type, where the shape predicates overlap or nest."""

    @pytest.mark.parametrize(
        ("tp", "kind"),
        [
            (Any, _TypeKind.ANY),
            (int | str, _TypeKind.UNION),
            (_Point, _TypeKind.NAMEDTUPLE),
            (tuple[int, int], _TypeKind.TUPLE),
            (_Config, _TypeKind.STRUCT),
            (list[int], _TypeKind.LIST),
            (list, _TypeKind.LIST),
            (Sequence[int], _TypeKind.LIST),
            (set[int], _TypeKind.SET),
            (set, _TypeKind.SET),
            (frozenset[int], _TypeKind.FROZENSET),
            (frozenset, _TypeKind.FROZENSET),
            (tuple, _TypeKind.TUPLE),
            (Mapping[str, int], _TypeKind.DICT),
            (dict, _TypeKind.DICT),
            (Callable[..., int], _TypeKind.CALLABLE),
            (Path, _TypeKind.LEAF),
            (UUID, _TypeKind.TAGGABLE_LEAF),
            (Decimal, _TypeKind.TAGGABLE_LEAF),
            (_Ticket, _TypeKind.STRUCT),
            (Literal["a"], _TypeKind.LEAF),
            (type[int], _TypeKind.LEAF),
            (_Alias, _TypeKind.LIST),
            (Annotated[_Point, "doc"], _TypeKind.NAMEDTUPLE),
        ],
    )
    def test_kind(self, tp: Any, kind: _TypeKind) -> None:
        """Each type takes exactly the branch its outermost shape names, its wrappers unwrapped."""
        assert _type_kind(tp) is kind

    def test_registered_leaf_with_init_params_is_a_taggable_leaf(self) -> None:
        """Registration moves a class with __init__ parameters from STRUCT to TAGGABLE_LEAF."""
        assert _type_kind(_Ticket) is _TypeKind.STRUCT
        confarg.register_leaf_type(_Ticket, _Ticket)
        assert _type_kind(_Ticket) is _TypeKind.TAGGABLE_LEAF


# ---------------------------------------------------------------------------
# TestRegistrationAfterIntrospection — the per-class caches never hold a leaf answer
# ---------------------------------------------------------------------------


class _Later:
    def __init__(self, raw: str) -> None:
        self.raw = raw

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Later) and other.raw == self.raw

    __hash__ = object.__hash__


@dataclass
class _HoldsLater:
    item: _Later


class TestRegistrationAfterIntrospection:
    """A type introspected as a struct becomes a leaf the moment it is registered (REF-48)."""

    def test_registering_after_a_build_takes_effect(self) -> None:
        """The struct answers for ``_Later`` are cached; the leaf decision must not be."""
        assert confarg.build(_HoldsLater, {"item": {"raw": "a"}}).item == _Later("a")
        confarg.register_leaf_type(_Later, _Later)
        assert confarg.build(_HoldsLater, {"item": "b"}).item == _Later("b")


# ---------------------------------------------------------------------------
# The date and time types — the grammars their coercions read (FEAT-51)
# ---------------------------------------------------------------------------

_H = timedelta(hours=1)


class TestParseDuration:
    """A duration is ISO 8601 text in its fixed units, read exactly."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("PT1H30M", timedelta(hours=1, minutes=30)),
            ("P1DT2H30M", timedelta(days=1, hours=2, minutes=30)),
            ("P2W", timedelta(days=14)),
            ("P1W2D", timedelta(days=9)),
            ("PT36H", timedelta(hours=36)),
            ("PT90M", timedelta(minutes=90)),
            ("PT1.5H", timedelta(hours=1.5)),
            ("P1.5D", timedelta(days=1, hours=12)),
            ("P1.1D", timedelta(days=1, seconds=8640)),
            ("PT0,5S", timedelta(milliseconds=500)),
            ("PT0.0000009S", timedelta(microseconds=1)),
            ("PT0.0000005S", timedelta(0)),
            ("PT0.0000015S", timedelta(microseconds=2)),
            ("-PT1H", -_H),
            ("-P1W", timedelta(days=-7)),
            ("pt1h", _H),
            ("Pt1H", _H),
            ("PT0S", timedelta(0)),
        ],
    )
    def test_reads(self, text: str, expected: timedelta) -> None:
        """Each part in its unit, a fraction on the last part only, rounded half-even to the microsecond."""
        assert _parse_duration(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "P",
            "PT",
            "P1DT",
            "-P",
            "P1M",
            "P1Y",
            "PT1.5H30M",
            "P-1D",
            "PT-1H",
            "+PT1H",
            "PT01:30:00",
            "1:30",
            "1:30:00",
            "90",
            "2 days, 0:00:00",
            "P1D2W",
            "PT1H ",
            " PT1H",
            "P999999999999D",
        ],
    )
    def test_refuses(self, text: str) -> None:
        """A variable unit, a fraction before the last part, a misplaced sign, any other form, an overflow."""
        with pytest.raises(ValueError, match=f"^{re.escape(text)}$"):
            _parse_duration(text)


class TestFormatDuration:
    """A duration is written as ISO 8601 text, days then the clock, each zero part left out."""

    @pytest.mark.parametrize(
        ("value", "text"),
        [
            (timedelta(days=1, hours=2), "P1DT2H"),
            (timedelta(days=1, hours=12), "P1DT12H"),
            (timedelta(minutes=1, seconds=30.5), "PT1M30.5S"),
            (timedelta(days=14), "P14D"),
            (timedelta(days=-1, seconds=1), "-PT23H59M59S"),
            (timedelta(hours=-1, minutes=-30), "-PT1H30M"),
            (timedelta(microseconds=1), "PT0.000001S"),
            (timedelta(0), "PT0S"),
            (timedelta.min, "-P999999999D"),
            (timedelta.max, "P999999999DT23H59M59.999999S"),
        ],
    )
    def test_writes(self, value: timedelta, text: str) -> None:
        """The text names the length, after a minus when negative."""
        assert _format_duration(value) == text

    @given(st.timedeltas())
    def test_reads_back(self, value: timedelta) -> None:
        """Every duration reads back from its text as itself."""
        assert _parse_duration(_format_duration(value)) == value


class TestTimezone:
    """A timezone is the UTC offset a datetime's text ends with."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Z", UTC),
            ("z", UTC),
            ("+00:00", UTC),
            ("-00:00", UTC),
            ("+02:00", timezone(2 * _H)),
            ("+0200", timezone(2 * _H)),
            ("+02", timezone(2 * _H)),
            ("-05:30", timezone(-timedelta(hours=5, minutes=30))),
            ("+02:00:30.5", timezone(timedelta(hours=2, seconds=30.5))),
            ("+23:59", timezone(timedelta(hours=23, minutes=59))),
        ],
    )
    def test_reads(self, text: str, expected: timezone) -> None:
        """``Z`` in either case, or a signed offset as ``datetime.fromisoformat`` reads one."""
        assert _coerce_timezone(text) == expected

    @pytest.mark.parametrize("text", ["UTC", "UTC+02:00", "+2", "02:00", "+24:00", "", ":30+02:00", "Zulu"])
    def test_refuses(self, text: str) -> None:
        """Python's ``str()`` of a timezone, an unsigned or short offset, and text around an offset."""
        with pytest.raises(ValueError, match="offset"):
            _coerce_timezone(text)

    @pytest.mark.parametrize(
        ("value", "text"),
        [
            (UTC, "+00:00"),
            (timezone(2 * _H, "CEST"), "+02:00"),
            (timezone(-timedelta(hours=5, minutes=30)), "-05:30"),
            (timezone(timedelta(seconds=30)), "+00:00:30"),
            (timezone(timedelta(seconds=30, microseconds=5)), "+00:00:30.000005"),
        ],
    )
    def test_writes_as_isoformat_does(self, value: timezone, text: str) -> None:
        """The offset ``datetime.isoformat()`` writes, a name never, and it reads back equal."""
        assert _format_offset(value) == text
        assert _coerce_timezone(text) == value


class TestRegisteredLeafOf:
    """An instance is its most specific registered leaf type (FEAT-51)."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (datetime(2021, 2, 3, 10), datetime),
            (date(2021, 2, 3), date),
            (Path("a"), Path),
            (Decimal(1), Decimal),
            (True, None),
            ("2021-02-03", None),
        ],
        ids=["datetime-not-date", "date", "path-subclass", "decimal", "bool", "str"],
    )
    def test_the_first_registered_class_of_the_mro(self, value: object, expected: type | None) -> None:
        """A ``datetime`` is no ``date`` here, a ``WindowsPath`` is a ``Path``, and a str is none."""
        assert _registered_leaf_of(value) is expected

    def test_an_instance_passes_through_its_own_type_only(self) -> None:
        """A ``datetime`` meets the ``date`` coercion, which refuses it, where a ``date`` passes through."""
        day = date(2021, 2, 3)
        assert _coerce_leaf(date, day) is day
        with pytest.raises(TypeCoercionError, match=r"Cannot coerce datetime .* to date"):
            _coerce_leaf(date, datetime(2021, 2, 3))

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for serialization: dump(), dump_file()."""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass as _dc
from dataclasses import field
from pathlib import Path
from typing import Any, Final, Literal, Optional, Union
from unittest import mock
from uuid import UUID

import pytest

import confarg
from confarg._serialize import _serialize_leaf, _serialize_untyped
from confarg._types import _Pinned, _StrToken, _UnionSeqToken
from confarg.exceptions import ConfargError, ConfargWarning
from tests.conftest import (
    AppConfig,
    CacheConfig,
    CircleShape,
    Color,
    DbConfig,
    DeepNested,
    Empty,
    Flat,
    IntColor,
    PgConfig,
    RectangleShape,
    RedisConfig,
    Release,
    ServerTcp,
    SquareShape,
    WithCollections,
    WithDefaults,
    WithNestedList,
    WithUnionAmbiguous,
    WithUnionAmbiguousThree,
    WithUnionDisjointDefaults,
    WithUnionOverlap,
    make_target,
)

# Module-level instances used in TestDumpLeafTypes parametrize
_DL_WithEnum = make_target("color", Color, default=Color.RED)
_DL_WithIntEnum = make_target("color", IntColor, default=IntColor.RED)
_DL_WithPath = make_target("location", Path, default=Path())
_DL_WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
_DL_WithNone = make_target("nothing", type(None), default=None)


# ---------------------------------------------------------------------------
# Basic dump
# ---------------------------------------------------------------------------


class TestDumpBasic:
    """Basic dump of flat and nested dataclasses."""

    def test_flat(self) -> None:
        """Flat dataclass serializes all fields."""
        obj = Flat(name="alice", count=3, rate=1.5, verbose=True)
        result = confarg.dump(obj)
        assert result == {"name": "alice", "count": 3, "rate": 1.5, "verbose": True}

    def test_defaults(self) -> None:
        """Dataclass with defaults serializes all fields including defaults."""
        obj = WithDefaults()
        result = confarg.dump(obj)
        assert result == {"name": "default", "count": 0, "rate": 1.0, "verbose": False}

    def test_empty(self) -> None:
        """Empty dataclass serializes to empty dict."""
        obj = Empty()
        result = confarg.dump(obj)
        assert result == {}

    def test_nested(self) -> None:
        """Nested dataclass serializes recursively."""
        obj = AppConfig(
            db=DbConfig(host="localhost", port=5432, name="mydb"),
            cache=CacheConfig(enabled=True, ttl=300),
            debug=False,
        )
        result = confarg.dump(obj)
        assert result == {
            "db": {"host": "localhost", "port": 5432, "name": "mydb"},
            "cache": {"enabled": True, "ttl": 300},
            "debug": False,
        }

    def test_deep_nested(self) -> None:
        """Three levels of nesting."""
        obj = DeepNested(
            app=AppConfig(
                db=DbConfig(host="h", port=1, name="n"),
                cache=CacheConfig(),
                debug=True,
            ),
            version="2.0",
        )
        result = confarg.dump(obj)
        assert result == {
            "app": {
                "db": {"host": "h", "port": 1, "name": "n"},
                "cache": {"enabled": True, "ttl": 300},
                "debug": True,
            },
            "version": "2.0",
        }


# ---------------------------------------------------------------------------
# Leaf types
# ---------------------------------------------------------------------------


class TestDumpLeafTypes:
    """Leaf value serialization."""

    @pytest.mark.parametrize(
        ("obj", "field", "expected"),
        [
            (Flat(name="x", count=42, rate=0.0, verbose=False), "count", 42),
            (Flat(name="x", count=0, rate=math.pi, verbose=False), "rate", math.pi),
            (Flat(name="x", count=0, rate=0.0, verbose=True), "verbose", True),
            (Flat(name="hello", count=0, rate=0.0, verbose=False), "name", "hello"),
            (_DL_WithEnum(color=Color.GREEN), "color", "green"),
            (_DL_WithIntEnum(color=IntColor.BLUE), "color", 3),
            (_DL_WithPath(location=Path("/tmp/foo")), "location", "/tmp/foo"),
            (_DL_WithLiteral(mode="slow"), "mode", "slow"),
            (_DL_WithNone(), "nothing", None),
        ],
        ids=["int", "float", "bool", "str", "enum", "int-enum", "path", "literal", "none"],
    )
    def test_leaf_passthrough(self, obj, field, expected) -> None:
        """Test that leaf fields are serialized to their native Python values."""
        assert confarg.dump(obj)[field] == expected

    @pytest.mark.parametrize(
        ("rate", "check"),
        [
            (float("inf"), math.isinf),
            (float("nan"), math.isnan),
        ],
        ids=["inf", "nan"],
    )
    def test_float_special(self, rate: float, check) -> None:
        """Test that special float values (inf, nan) are preserved during serialization."""
        result = confarg.dump(Flat(name="x", count=0, rate=rate, verbose=False))
        assert check(result["rate"])


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


class TestDumpCollections:
    """Collection serialization."""

    def test_list(self) -> None:
        """Test that a list field serializes to a list."""
        WithList = make_target("items", list[int], default_factory=list)
        obj = WithList(items=[1, 2, 3])
        result = confarg.dump(obj)
        assert result["items"] == [1, 2, 3]

    def test_set_sorted(self) -> None:
        """Set serializes to a sorted list."""
        WithSet = make_target("tags", set[str], default_factory=set)
        obj = WithSet(tags={"c", "a", "b"})
        result = confarg.dump(obj)
        assert result["tags"] == ["a", "b", "c"]

    def test_frozenset_sorted(self) -> None:
        """Frozenset serializes to a sorted list."""
        WithFrozenSet = make_target("tags", frozenset[str], default_factory=frozenset)
        obj = WithFrozenSet(tags=frozenset({"z", "m", "a"}))
        result = confarg.dump(obj)
        assert result["tags"] == ["a", "m", "z"]

    def test_tuple_to_list(self) -> None:
        """Tuple serializes to a list."""
        WithTuple = make_target("pair", tuple[str, int], default=("", 0))
        obj = WithTuple(pair=("hello", 42))
        result = confarg.dump(obj)
        assert result["pair"] == ["hello", 42]

    def test_dict(self) -> None:
        """Test that a dict field serializes to a dict."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        obj = WithDict(metadata={"a": 1, "b": 2})
        result = confarg.dump(obj)
        assert result["metadata"] == {"a": 1, "b": 2}

    def test_list_of_dataclasses(self) -> None:
        """List of dataclasses serializes each element."""
        obj = WithNestedList(
            servers=[
                DbConfig(host="a", port=1, name="db1"),
                DbConfig(host="b", port=2, name="db2"),
            ],
        )
        result = confarg.dump(obj)
        assert result["servers"] == [
            {"host": "a", "port": 1, "name": "db1"},
            {"host": "b", "port": 2, "name": "db2"},
        ]

    def test_empty_collections(self) -> None:
        """Test that empty collection fields serialize to empty containers."""
        obj = WithCollections()
        result = confarg.dump(obj)
        assert result == {"names": [], "counts": [], "tags": [], "mapping": {}}


# ---------------------------------------------------------------------------
# Optional
# ---------------------------------------------------------------------------


class TestDumpOptional:
    """Optional field serialization."""

    def test_none_included(self) -> None:
        """Test that an Optional field with None value serializes as None."""
        WithOptional = make_target("value", int | None, default=None)
        obj = WithOptional(value=None)
        result = confarg.dump(obj)
        assert result["value"] is None

    def test_present_value(self) -> None:
        """Test that an Optional field with a value serializes correctly."""
        WithOptional = make_target("value", int | None, default=None)
        obj = WithOptional(value=42)
        result = confarg.dump(obj)
        assert result["value"] == 42

    def test_optional_str_none(self) -> None:
        """Test that an Optional[str] field with None value serializes as None."""
        WithOptionalStr = make_target("value", str | None, default=None)
        obj = WithOptionalStr(value=None)
        result = confarg.dump(obj)
        assert result["value"] is None

    def test_optional_str_present(self) -> None:
        """Test that an Optional[str] field with a present value serializes correctly."""
        WithOptionalStr = make_target("value", str | None, default=None)
        obj = WithOptionalStr(value="hello")
        result = confarg.dump(obj)
        assert result["value"] == "hello"


# ---------------------------------------------------------------------------
# Union tag_policy="always"
# ---------------------------------------------------------------------------


class TestDumpUnionTagAlways:
    """Union serialization with tag_policy='always'."""

    def test_tag_always_present_on_dc_union(self) -> None:
        """Dataclass union values always get a class tag."""
        obj = WithUnionAmbiguous(shape=CircleShape(x=1, y=2, radius=5))
        result = confarg.dump(obj, tag_policy="always")
        assert result["shape"]["class"] == "tests.conftest.CircleShape"

    def test_tag_always_square(self) -> None:
        """Test that a SquareShape value always gets a class tag."""
        obj = WithUnionAmbiguous(shape=SquareShape(x=0, y=0, radius=3))
        result = confarg.dump(obj, tag_policy="always")
        assert result["shape"]["class"] == "tests.conftest.SquareShape"

    def test_tag_always_not_on_leaf_union(self) -> None:
        """Leaf union values do not get a class tag."""
        WithUnionThree = make_target("value", Union[int, float, str], default=0)
        obj = WithUnionThree(value=42)
        result = confarg.dump(obj, tag_policy="always")
        assert result["value"] == 42
        assert not isinstance(result["value"], dict)

    def test_custom_union_tag(self) -> None:
        """Custom union_tag name is used."""
        obj = WithUnionAmbiguous(shape=CircleShape(x=1, y=2, radius=5))
        result = confarg.dump(obj, union_tag="type", tag_policy="always")
        assert result["shape"]["type"] == "tests.conftest.CircleShape"
        assert "class" not in result["shape"]


# ---------------------------------------------------------------------------
# Union tag_policy="auto"
# ---------------------------------------------------------------------------


class TestDumpUnionTagAuto:
    """Union serialization with tag_policy='auto' (default)."""

    def test_ambiguous_gets_tag(self) -> None:
        """CircleShape/SquareShape are structurally identical -> tag needed."""
        obj = WithUnionAmbiguous(shape=CircleShape(x=1, y=2, radius=5))
        result = confarg.dump(obj)
        assert result["shape"]["class"] == "tests.conftest.CircleShape"

    def test_ambiguous_square_gets_tag(self) -> None:
        """Test that an ambiguous SquareShape gets a class tag under auto policy."""
        obj = WithUnionAmbiguous(shape=SquareShape(x=0, y=0, radius=3))
        result = confarg.dump(obj)
        assert result["shape"]["class"] == "tests.conftest.SquareShape"

    def test_unambiguous_no_tag(self) -> None:
        """PgConfig/RedisConfig have disjoint fields -> no tag needed."""
        obj = WithUnionDisjointDefaults(backend=PgConfig(host="h", port=5432, sslmode="require"))
        result = confarg.dump(obj)
        assert "class" not in result["backend"]
        assert result["backend"]["sslmode"] == "require"

    def test_unambiguous_redis_no_tag(self) -> None:
        """Test that an unambiguous RedisConfig value gets no class tag."""
        obj = WithUnionDisjointDefaults(backend=RedisConfig(host="h", port=6379, db=1))
        result = confarg.dump(obj)
        assert "class" not in result["backend"]
        assert result["backend"]["db"] == 1

    def test_overlapping_native_int_no_tag(self) -> None:
        """ServerTcp has int port -> native int disambiguates, no tag needed."""
        obj = WithUnionOverlap(server=ServerTcp(host="h", port=5432))
        result = confarg.dump(obj)
        assert "class" not in result["server"]

    def test_leaf_union_no_tag(self) -> None:
        """Leaf unions never get a tag."""
        WithUnionIntFloat = make_target("value", Union[int, float], default=0)
        obj = WithUnionIntFloat(value=math.pi)
        result = confarg.dump(obj)
        assert result["value"] == math.pi

    def test_three_way_rectangle_no_tag(self) -> None:
        """RectangleShape is structurally unique in the three-way union -> no tag."""
        obj = WithUnionAmbiguousThree(shape=RectangleShape(x=0, y=0, width=10, height=20))
        result = confarg.dump(obj)
        assert "class" not in result["shape"]

    def test_three_way_circle_gets_tag(self) -> None:
        """CircleShape is ambiguous with SquareShape in three-way -> tag needed."""
        obj = WithUnionAmbiguousThree(shape=CircleShape(x=1, y=2, radius=5))
        result = confarg.dump(obj)
        assert result["shape"]["class"] == "tests.conftest.CircleShape"


# ---------------------------------------------------------------------------
# Leaf variants a sibling would steal back
# ---------------------------------------------------------------------------


class TestDumpStolenLeaf:
    """A leaf value another union variant would steal back dumps with its ``__cast__``."""

    def test_enum_variant_would_steal_the_string(self) -> None:
        """A str beside an Enum that accepts it dumps cast, so it reads back as a str."""
        WithColorOrStr = make_target("value", Union[Color, str], default="red")
        obj = WithColorOrStr(value="red")
        result = confarg.dump(obj)
        assert result["value"] == {"__cast__": "str", "__value__": "red"}
        assert confarg.build(WithColorOrStr, result) == obj

    def test_registered_leaf_variant_would_steal_the_string(self) -> None:
        """A str beside a Path variant dumps cast: Path would take the bare scalar."""
        WithPathOrStr = make_target("value", Union[Path, str], default="")
        obj = WithPathOrStr(value="subdir")
        result = confarg.dump(obj)
        assert result["value"] == {"__cast__": "str", "__value__": "subdir"}
        assert confarg.build(WithPathOrStr, result) == obj

    def test_enum_variant_would_steal_the_int(self) -> None:
        """An int beside an IntEnum that accepts it dumps cast."""
        WithIntColorOrInt = make_target("value", Union[IntColor, int], default=0)
        obj = WithIntColorOrInt(value=1)
        result = confarg.dump(obj)
        assert result["value"] == {"__cast__": "int", "__value__": 1}
        built = confarg.build(WithIntColorOrInt, result)
        assert type(built.value) is int

    def test_value_that_reads_back_stays_bare(self) -> None:
        """The Enum member itself is not stolen from, so it keeps the bare form."""
        WithColorOrStr = make_target("value", Union[Color, str], default="red")
        obj = WithColorOrStr(value=Color.RED)
        result = confarg.dump(obj)
        assert result["value"] == "red"
        assert confarg.build(WithColorOrStr, result) == obj

    def test_unstealable_leaf_union_stays_bare(self) -> None:
        """A union no variant can steal from dumps bare scalars as before."""
        WithIntOrFloat = make_target("value", Union[int, float], default=0)
        result = confarg.dump(WithIntOrFloat(value=math.pi))
        assert result["value"] == pytest.approx(math.pi)

    def test_inexpressible_cast_warns_and_dumps_bare(self) -> None:
        """No __cast__ can name an unregistered Enum, so dump warns instead of lying."""
        WithStrOrColor = make_target("value", Union[str, Color], default="plain")
        obj = WithStrOrColor(value=Color.RED)
        with pytest.warns(ConfargWarning, match="value"):
            result = confarg.dump(obj)
        assert result["value"] == "red"

    def test_tag_policy_always_does_not_cast_an_unstolen_leaf(self) -> None:
        """'always' is a class-tag policy: a leaf that reads back stays bare under it too."""
        WithColorOrStr = make_target("value", Union[Color, str], default="red")
        result = confarg.dump(WithColorOrStr(value=Color.RED), tag_policy="always")
        assert result["value"] == "red"

    def test_stolen_leaf_round_trips_through_a_file(self, tmp_path: Path) -> None:
        """dump_file writes the cast form and load reads the same object back."""
        WithColorOrStr = make_target("value", Union[Color, str], default="red")
        obj = WithColorOrStr(value="red")
        path = tmp_path / "out.yaml"
        confarg.dump_file(obj, path)
        assert confarg.load(WithColorOrStr, argv=[], env={}, files=[path]) == obj


# ---------------------------------------------------------------------------
# A union with an Any variant (BUG-117)
# ---------------------------------------------------------------------------


@_dc
class _AnyPeer:
    a: int = 0


class TestDumpUnionWithAny:
    """``Any`` holds every value, so ``dump()`` picks it last and writes it as a bare ``Any`` field does."""

    def test_the_ticket_reproduction(self) -> None:
        """``list[int] | Any`` holding 3 dumps the 3 and builds back, not a TypeError."""
        WithListOrAny = make_target("x", Union[list[int], Any], default=None)
        obj = WithListOrAny(x=3)
        assert confarg.dump(obj) == {"x": 3}
        assert confarg.build(WithListOrAny, confarg.dump(obj)) == obj

    @pytest.mark.parametrize("tp", [Optional[Any], Union[int, Any], Union[Any, int]])
    def test_a_value_only_any_holds_dumps_as_itself(self, tp: Any) -> None:
        """A str nothing else holds dumps bare and builds back."""
        Target = make_target("x", tp, default=None)
        obj = Target(x="abc")
        assert confarg.dump(obj) == {"x": "abc"}
        assert confarg.build(Target, confarg.dump(obj)) == obj

    @pytest.mark.parametrize("tp", [Union[_AnyPeer, Any], Union[Any, _AnyPeer]])
    def test_a_struct_dumps_as_its_variant(self, tp: Any) -> None:
        """A struct held beside Any dumps its fields, whichever side Any is written on."""
        Target = make_target("x", tp, default=None)
        obj = Target(x=_AnyPeer(a=1))
        assert confarg.dump(obj) == {"x": {"a": 1}}
        assert confarg.build(Target, confarg.dump(obj)) == obj

    @pytest.mark.parametrize("tp", [Union[Path, Any], Union[Any, Path]])
    def test_a_str_the_typed_variant_would_steal_dumps_cast(self, tp: Any) -> None:
        """A str that Path would take back dumps with its cast, and reads back as the str."""
        Target = make_target("x", tp, default=None)
        obj = Target(x="a")
        assert confarg.dump(obj) == {"x": {"__cast__": "str", "__value__": "a"}}
        assert confarg.build(Target, confarg.dump(obj)) == obj

    def test_a_dict_a_struct_variant_would_take_warns(self) -> None:
        """No __cast__ names a dict, so a dict the struct would take back is written bare, with a warning."""
        Target = make_target("x", Union[_AnyPeer, Any], default=None)
        with pytest.warns(ConfargWarning, match="'x'"):
            result = confarg.dump(Target(x={"a": 1}))
        assert result == {"x": {"a": 1}}


@_dc
class _AnyHeld:
    a: int = 0


@_dc
class _AnyHeldAny:
    p: Any = None


class _AnyScaler:
    """A plain callable class with no ``__eq__``: it reads back as an object holding the same state."""

    def __init__(self, factor: int) -> None:
        self.factor = factor

    def __call__(self, x: int) -> int:
        return x * self.factor


class _AnyHidden:
    """Keeps its argument under another name, so no spec can rebuild it."""

    def __init__(self, factor: int) -> None:
        self._factor = factor


def _any_double(x: int) -> int:
    return 2 * x


_MOD = __name__


class TestDumpAny:
    """An object an ``Any`` field holds dumps by its runtime type, as the spec that rebuilds it (FEAT-42)."""

    def test_the_ticket_reproduction(self) -> None:
        """A struct default dumps as its class spec, a Path as its text with a warning."""
        Target = make_target("y", Any, default_factory=lambda: _AnyHeld(1))
        assert confarg.dump(Target()) == {"y": {"class": f"{_MOD}._AnyHeld", "a": 1}}
        assert confarg.build(Target, confarg.dump(Target())) == Target()

    def test_a_value_that_reads_back_as_another_type_warns(self) -> None:
        """A Path reads back as a str under Any, so it is written as its text, with a warning naming the field."""
        Target = make_target("x", Any, default_factory=lambda: [Path("p")])
        with pytest.warns(ConfargWarning, match=r"'x\[0\]'"):
            assert confarg.dump(Target()) == {"x": ["p"]}

    def test_a_plain_value_dumps_without_a_warning(self, recwarn: pytest.WarningsRecorder) -> None:
        """An int, a str, a list and a dict of them read back as themselves."""
        Target = make_target("x", Any, default=None)
        obj = Target(x={"a": [1, "b", 2.5, True, None]})
        assert confarg.dump(obj) == {"x": {"a": [1, "b", 2.5, True, None]}}
        assert not [w for w in recwarn if issubclass(w.category, ConfargWarning)]

    def test_an_object_nested_in_containers_dumps_as_its_spec(self) -> None:
        """Specs are written at every depth."""
        Target = make_target("x", Any, default=None)
        obj = Target(x={"k": [_AnyHeld(2)]})
        assert confarg.dump(obj) == {"x": {"k": [{"class": f"{_MOD}._AnyHeld", "a": 2}]}}
        assert confarg.build(Target, confarg.dump(obj)) == obj

    def test_a_function_dumps_as_a_bind_spec(self) -> None:
        """A bare path would read back as text, so a function is written under bind:."""
        Target = make_target("x", Any, default=None)
        dumped = confarg.dump(Target(x=_any_double))
        assert dumped == {"x": {"bind": f"{_MOD}._any_double"}}
        assert confarg.build(Target, dumped).x is _any_double

    def test_a_partial_dumps_as_a_bind_spec_with_its_arguments(self) -> None:
        """A partial is written as a Callable field writes it."""
        import functools  # noqa: PLC0415  # used by this test only

        Target = make_target("x", Any, default=None)
        dumped = confarg.dump(Target(x=functools.partial(_any_double, x=3)))
        assert dumped == {"x": {"bind": f"{_MOD}._any_double", "args": {"x": 3}}}
        assert confarg.build(Target, dumped).x() == 6

    def test_an_object_with_no_eq_reads_back_by_its_state(self) -> None:
        """A plain class with no __eq__ is kept: it reads back as an object holding the same state."""
        Target = make_target("x", Any, default=None)
        dumped = confarg.dump(Target(x=_AnyScaler(3)))
        assert dumped == {"x": {"class": f"{_MOD}._AnyScaler", "factor": 3}}
        assert confarg.build(Target, dumped).x(2) == 6

    def test_an_object_no_spec_rebuilds_is_written_untyped_with_a_warning(self) -> None:
        """An object whose state cannot be read is written as it is, with a warning saying why."""
        Target = make_target("x", Any, default=None)
        held = _AnyHidden(3)
        with pytest.warns(ConfargWarning, match="'x'"):
            assert confarg.dump(Target(x=held)) == {"x": held}

    def test_a_failed_spec_warns_once(self) -> None:
        """A UUID is no spec: one warning names the value, none its would-be fields."""
        Target = make_target("x", Any, default=None)
        with pytest.warns(ConfargWarning) as record:
            confarg.dump(Target(x=UUID(int=1)))
        assert [str(w.message).split("'")[1] for w in record] == ["x"]

    def test_a_kept_spec_still_says_what_its_fields_warn(self) -> None:
        """A struct whose Any field holds a Path is kept, and the Path still warns."""
        Target = make_target("x", Any, default=None)
        with pytest.warns(ConfargWarning, match=r"'x\.p'"):
            dumped = confarg.dump(Target(x=_AnyHeldAny(p=Path("q"))))
        assert dumped == {"x": {"class": f"{_MOD}._AnyHeldAny", "p": "q"}}

    def test_a_dict_holding_an_opener_warns(self) -> None:
        """A dict holding a class key reads back as a spec, not as the dict, so it warns."""
        Target = make_target("x", Any, default=None)
        with pytest.warns(ConfargWarning, match="'x'"):
            assert confarg.dump(Target(x={"class": "not.a.Class"})) == {"x": {"class": "not.a.Class"}}

    @pytest.mark.parametrize("tp", [Union[int, Any], Union[_AnyPeer, Any]])
    def test_an_object_beside_a_typed_variant_dumps_as_its_spec(self, tp: Any) -> None:
        """Beside int or another struct, an object only Any holds is written as its class spec."""
        Target = make_target("x", tp, default=None)
        obj = Target(x=_AnyHeld(4))
        assert confarg.dump(obj) == {"x": {"class": f"{_MOD}._AnyHeld", "a": 4}}
        assert confarg.build(Target, confarg.dump(obj)) == obj

    def test_a_list_of_any_dumps_each_element_as_its_spec(self) -> None:
        """list[Any] elements are Any nodes."""
        Target = make_target("x", list[Any], default_factory=list)
        obj = Target(x=[_AnyHeld(1), 2])
        assert confarg.dump(obj) == {"x": [{"class": f"{_MOD}._AnyHeld", "a": 1}, 2]}
        assert confarg.build(Target, confarg.dump(obj)) == obj


# ---------------------------------------------------------------------------
# Subscripted and Literal union variants
# ---------------------------------------------------------------------------


class TestDumpSubscriptedUnionVariant:
    """A union variant ``isinstance`` refuses — a parameterized generic, a Literal — still dumps."""

    def test_list_variant_dumps_as_a_list(self) -> None:
        """``list[str] | str`` holding a list dumps the list, not a TypeError."""
        WithListOrStr = make_target("tags", Union[list[str], str], default_factory=list)
        obj = WithListOrStr(tags=["a", "b"])
        assert confarg.dump(obj) == {"tags": ["a", "b"]}
        assert confarg.build(WithListOrStr, confarg.dump(obj)) == obj

    def test_scalar_beside_a_list_variant_dumps_as_a_scalar(self) -> None:
        """The str side of ``list[str] | str`` is unaffected by the list variant."""
        WithListOrStr = make_target("tags", Union[list[str], str], default_factory=list)
        obj = WithListOrStr(tags="a")
        assert confarg.dump(obj) == {"tags": "a"}
        assert confarg.build(WithListOrStr, confarg.dump(obj)) == obj

    def test_set_variant_dumps_as_a_sorted_list(self) -> None:
        """``set[str] | str`` holding a set dumps the deterministic list form."""
        WithSetOrStr = make_target("tags", Union[set[str], str], default_factory=set)
        obj = WithSetOrStr(tags={"b", "a"})
        assert confarg.dump(obj) == {"tags": ["a", "b"]}
        assert confarg.build(WithSetOrStr, confarg.dump(obj)) == obj

    def test_frozenset_variant_dumps_as_a_sorted_list(self) -> None:
        """A frozenset variant is told apart from the set and list ones by its own shape."""
        WithFrozenOrStr = make_target("tags", Union[frozenset[str], str], default_factory=frozenset)
        obj = WithFrozenOrStr(tags=frozenset({"b", "a"}))
        assert confarg.dump(obj) == {"tags": ["a", "b"]}
        assert confarg.build(WithFrozenOrStr, confarg.dump(obj)) == obj

    def test_variable_length_tuple_variant_dumps_as_a_list(self) -> None:
        """``tuple[int, ...]`` takes any arity, unlike the fixed-length spelling."""
        WithVarTupleOrStr = make_target("nums", Union[tuple[int, ...], str], default="")
        obj = WithVarTupleOrStr(nums=(1, 2, 3))
        assert confarg.dump(obj) == {"nums": [1, 2, 3]}
        assert confarg.build(WithVarTupleOrStr, confarg.dump(obj)) == obj

    def test_dict_variant_dumps_as_a_dict(self) -> None:
        """``dict[str, int] | str`` holding a mapping dumps the mapping."""
        WithDictOrStr = make_target("opts", Union[dict[str, int], str], default="")
        obj = WithDictOrStr(opts={"a": 1})
        assert confarg.dump(obj) == {"opts": {"a": 1}}
        assert confarg.build(WithDictOrStr, confarg.dump(obj)) == obj

    def test_tuple_variant_dumps_as_a_list(self) -> None:
        """A fixed-length tuple variant dumps as the list a file spells it with."""
        WithTupleOrStr = make_target("pair", Union[tuple[int, int], str], default="")
        obj = WithTupleOrStr(pair=(1, 2))
        assert confarg.dump(obj) == {"pair": [1, 2]}
        assert confarg.build(WithTupleOrStr, confarg.dump(obj)) == obj

    def test_literal_variant_dumps_as_a_scalar(self) -> None:
        """A Literal member is a plain scalar, so it serializes as one."""
        WithLiteralOrStr = make_target("speed", Union[Literal["fast", "slow"], str], default="fast")
        obj = WithLiteralOrStr(speed="fast")
        assert confarg.dump(obj) == {"speed": "fast"}
        assert confarg.build(WithLiteralOrStr, confarg.dump(obj)) == obj

    def test_value_outside_the_literal_dumps_as_the_other_variant(self) -> None:
        """A value no Literal member holds belongs to the sibling variant."""
        WithLiteralOrStr = make_target("speed", Union[Literal["fast", "slow"], str], default="fast")
        obj = WithLiteralOrStr(speed="other")
        assert confarg.dump(obj) == {"speed": "other"}
        assert confarg.build(WithLiteralOrStr, confarg.dump(obj)) == obj

    def test_enum_literal_variant_dumps_as_its_value(self) -> None:
        """A Literal over Enum members dumps the member's value, like a bare Enum does.

        The value reads back as the member: a native string carrying the Enum
        value builds the Literal-over-Enum (BUG-32), so no warning and no
        ``__cast__`` is needed.
        """
        WithEnumLiteralOrInt = make_target("color", Union[Literal[Color.RED], int], default=0)
        obj = WithEnumLiteralOrInt(color=Color.RED)
        result = confarg.dump(obj)
        assert result == {"color": "red"}
        assert confarg.build(WithEnumLiteralOrInt, result) == obj

    def test_bool_is_not_a_member_of_an_int_literal(self) -> None:
        """``Literal[1] | bool`` holding True is the bool variant: True is not the member 1."""
        WithIntLiteralOrBool = make_target("flag", Union[Literal[1], bool], default=1)
        obj = WithIntLiteralOrBool(flag=True)
        assert confarg.dump(obj) == {"flag": True}
        assert confarg.build(WithIntLiteralOrBool, confarg.dump(obj)) == obj

    def test_list_variant_beside_a_struct_variant(self) -> None:
        """A struct variant still wins its own instances when a generic sits beside it."""
        WithListOrCfg = make_target("item", Union[list[str], CacheConfig], default_factory=list)
        obj = WithListOrCfg(item=CacheConfig())
        assert confarg.dump(obj)["item"] == confarg.dump(CacheConfig())


# ---------------------------------------------------------------------------
# Subclass serialization
# ---------------------------------------------------------------------------


@_dc
class _SubBase:
    pass


@_dc
class _SubChild(_SubBase):
    value: float


@_dc
class _SubWrapper:
    item: _SubBase


class _SubOuter:
    """Holder whose nested subclass is only reachable through its own qualified name."""

    @_dc
    class Nested(_SubBase):
        value: float = 0.0


class TestDumpSubclass:
    """Serialization of dataclass subclasses held via a base-class field."""

    def test_nested_class_tag_is_the_qualified_name(self) -> None:
        """A class nested inside a class is tagged with the path that imports it back."""
        obj = _SubWrapper(item=_SubOuter.Nested(value=1.0))
        result = confarg.dump(obj)
        assert result["item"]["class"] == "tests.test_serialize._SubOuter.Nested"

    def test_nested_class_tag_round_trips(self) -> None:
        """The tag dump() writes for a nested class is one from_dict() can read back."""
        obj = _SubWrapper(item=_SubOuter.Nested(value=2.5))
        loaded = confarg.from_dict(_SubWrapper, confarg.dump(obj))
        assert isinstance(loaded.item, _SubOuter.Nested)
        assert loaded.item.value == pytest.approx(2.5)

    def test_a_class_tag_naming_a_class_defined_in_a_function_cannot_be_dumped(self) -> None:
        """A tag whose path holds ``<locals>`` is refused at dump(), not on read-back (BUG-193).

        Both writers of a tag: the subclass a struct field holds, and the variant of a union.
        """

        @_dc
        class Local(_SubBase):
            value: float

        @_dc
        class Left:
            x: int

        @_dc
        class Right:
            x: int

        with pytest.raises(ConfargError, match=r"does not import back as it"):
            confarg.dump(_SubWrapper(item=Local(value=1.0)))
        with pytest.raises(ConfargError, match=r"does not import back as it"):
            confarg.dump(make_target("v", Left | Right)(v=Right(x=1)))

    def test_subclass_fields_and_tag_emitted(self) -> None:
        """When a field typed Foo holds a Bar(Foo) instance, Bar's fields and a type tag are serialized."""
        obj = _SubWrapper(item=_SubChild(value=1.0))
        result = confarg.dump(obj)
        assert result["item"]["value"] == pytest.approx(1.0)
        assert result["item"]["class"] == "tests.test_serialize._SubChild"

    def test_subclass_round_trip(self, tmp_path: Path) -> None:
        """dump_yaml then load round-trips a subclass instance correctly."""
        obj = _SubWrapper(item=_SubChild(value=2.5))
        path = tmp_path / "out.yaml"
        confarg.dump_file(obj, path)
        loaded = confarg.load(_SubWrapper, argv=[], env={}, files=[path])
        assert isinstance(loaded.item, _SubChild)
        assert loaded.item.value == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# dump_toml
# ---------------------------------------------------------------------------


class TestDumpToml:
    """TOML dump and roundtrip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        """dump_toml then load produces same data."""
        obj = AppConfig(
            db=DbConfig(host="localhost", port=5432, name="mydb"),
            cache=CacheConfig(enabled=True, ttl=600),
            debug=True,
        )
        path = tmp_path / "out.toml"
        confarg.dump_file(obj, path)
        loaded = confarg.load(AppConfig, argv=[], env={}, files=[path])
        assert loaded.db.host == "localhost"
        assert loaded.db.port == 5432
        assert loaded.cache.ttl == 600
        assert loaded.debug is True

    def test_inf_nan_roundtrip(self, tmp_path: Path) -> None:
        """TOML supports inf/nan natively."""
        obj = Flat(name="x", count=0, rate=float("inf"), verbose=False)
        path = tmp_path / "out.toml"
        confarg.dump_file(obj, path)
        loaded = confarg.load(Flat, argv=[], env={}, files=[path])
        assert loaded.rate == float("inf")

    def test_missing_tomli_w(self, tmp_path: Path) -> None:
        """Raises InvalidConfigFileError when tomli_w is not installed."""
        obj = Empty()
        path = tmp_path / "out.toml"
        with (
            mock.patch.dict(sys.modules, {"tomli_w": None}),
            pytest.raises(confarg.exceptions.InvalidConfigFileError, match="tomli_w"),
        ):
            confarg.dump_file(obj, path)


# ---------------------------------------------------------------------------
# dump_yaml
# ---------------------------------------------------------------------------


class TestDumpYaml:
    """YAML dump and roundtrip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        """dump_yaml then load produces same data."""
        obj = AppConfig(
            db=DbConfig(host="localhost", port=5432, name="mydb"),
            cache=CacheConfig(enabled=True, ttl=600),
            debug=True,
        )
        path = tmp_path / "out.yaml"
        confarg.dump_file(obj, path)
        loaded = confarg.load(AppConfig, argv=[], env={}, files=[path])
        assert loaded.db.host == "localhost"
        assert loaded.db.port == 5432
        assert loaded.cache.ttl == 600
        assert loaded.debug is True

    def test_inf_nan_roundtrip(self, tmp_path: Path) -> None:
        """YAML supports inf/nan natively."""
        obj = Flat(name="x", count=0, rate=float("inf"), verbose=False)
        path = tmp_path / "out.yaml"
        confarg.dump_file(obj, path)
        loaded = confarg.load(Flat, argv=[], env={}, files=[path])
        assert loaded.rate == float("inf")

    def test_missing_pyyaml(self, tmp_path: Path) -> None:
        """Raises InvalidConfigFileError when PyYAML is not installed."""
        obj = Empty()
        path = tmp_path / "out.yaml"
        with (
            mock.patch.dict(sys.modules, {"yaml": None}),
            pytest.raises(confarg.exceptions.InvalidConfigFileError, match="PyYAML"),
        ):
            confarg.dump_file(obj, path)

    def test_raw_dict_tuple_is_written_as_a_list(self, tmp_path: Path) -> None:
        """A raw dict's tuple is written as a plain list, never the `!!python/tuple` tag.

        SafeDumper's spelling; the default Dumper would emit a tag the reader's
        `yaml.safe_load` refuses.
        """
        path = tmp_path / "out.yaml"
        confarg.dump_file({"items": (1, 2)}, path)
        assert path.read_bytes() == b"items:\n- 1\n- 2\n"

    def test_non_ascii_is_written_as_utf_8(self, tmp_path: Path) -> None:
        r"""Non-ASCII text reaches the file as raw UTF-8 bytes, not `\x` escapes."""
        path = tmp_path / "out.yaml"
        confarg.dump_file({"name": "naïve"}, path)
        assert path.read_bytes() == b"name: " + "naïve".encode() + b"\n"
        target = make_target("name", str, default="")
        assert confarg.load(target, argv=[], env={}, files=[path]).name == "naïve"


# ---------------------------------------------------------------------------
# dump_json
# ---------------------------------------------------------------------------


class TestDumpJson:
    """JSON dump: the bytes it writes."""

    def test_indent_is_two_spaces(self, tmp_path: Path) -> None:
        """A member one level down is indented by exactly the declared two spaces."""
        path = tmp_path / "out.json"
        confarg.dump_file({"db": {"host": "h"}}, path)
        assert path.read_bytes() == b'{\n  "db": {\n    "host": "h"\n  }\n}'

    def test_non_ascii_is_written_as_utf_8(self, tmp_path: Path) -> None:
        r"""Non-ASCII text reaches the file as raw UTF-8 bytes, not `\u` escapes."""
        path = tmp_path / "out.json"
        confarg.dump_file({"name": "naïve"}, path)
        assert path.read_bytes() == b'{\n  "name": "' + "naïve".encode() + b'"\n}'
        target = make_target("name", str, default="")
        assert confarg.load(target, argv=[], env={}, files=[path]).name == "naïve"


# ---------------------------------------------------------------------------
# Roundtrip: load -> dump -> load
# ---------------------------------------------------------------------------


class TestDumpRoundTrip:
    """Load -> dump -> load produces the same result."""

    def test_flat_roundtrip(self, tmp_path: Path) -> None:
        """Test that a flat dataclass round-trips through load → dump → load."""
        path_in = tmp_path / "in.toml"
        path_in.write_text('name = "alice"\ncount = 3\nrate = 1.5\nverbose = true\n')
        obj = confarg.load(Flat, argv=[], env={}, files=[path_in])
        path_out = tmp_path / "out.toml"
        confarg.dump_file(obj, path_out)
        obj2 = confarg.load(Flat, argv=[], env={}, files=[path_out])
        assert obj == obj2

    def test_nested_roundtrip(self, tmp_path: Path) -> None:
        """Test that a nested dataclass round-trips through load → dump → load."""
        obj = AppConfig(
            db=DbConfig(host="h", port=1, name="n"),
            cache=CacheConfig(enabled=False, ttl=0),
            debug=True,
        )
        path = tmp_path / "out.yaml"
        confarg.dump_file(obj, path)
        obj2 = confarg.load(AppConfig, argv=[], env={}, files=[path])
        assert obj == obj2

    def test_collections_roundtrip(self, tmp_path: Path) -> None:
        """Test that a dict field round-trips through load → dump → load."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        obj = WithDict(metadata={"a": 1, "b": 2})
        path = tmp_path / "out.toml"
        confarg.dump_file(obj, path)
        obj2 = confarg.load(WithDict, argv=[], env={}, files=[path])
        assert obj == obj2

    def test_enum_roundtrip(self, tmp_path: Path) -> None:
        """Test that an Enum field round-trips through load → dump → load."""
        WithEnum = make_target("color", Color, default=Color.RED)
        obj = WithEnum(color=Color.BLUE)
        path = tmp_path / "out.toml"
        confarg.dump_file(obj, path)
        obj2 = confarg.load(WithEnum, argv=[], env={}, files=[path])
        assert obj == obj2

    def test_union_with_tag_roundtrip(self, tmp_path: Path) -> None:
        """Ambiguous union roundtrips via tag."""
        obj = WithUnionAmbiguous(shape=SquareShape(x=0, y=0, radius=3))
        path = tmp_path / "out.toml"
        confarg.dump_file(obj, path)
        obj2 = confarg.load(WithUnionAmbiguous, argv=[], env={}, files=[path])
        assert isinstance(obj2.shape, SquareShape)
        assert obj2.shape.radius == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Raw merged dicts: coerced leaves
# ---------------------------------------------------------------------------


class TestDumpRawDictCoercedLeaves:
    """dump_file(raw_dict) writes a ``Path`` or an ``Enum`` member a dict holds as the scalar a file carries.

    ``merge()`` holds such a leaf as it was written (BUG-246), but a caller's own dict may
    hold the object. The dict path applies the same leaf rules as ``dump()``.
    """

    @pytest.mark.parametrize("suffix", [".toml", ".yaml", ".json"])
    def test_path_leaf(self, tmp_path: Path, suffix: str) -> None:
        """A Path dumps as its forward-slash form, in every format."""
        WithPath = make_target("out", Path, default=Path("default.txt"))
        path = tmp_path / f"out{suffix}"
        confarg.dump_file({"out": Path("sub/x.txt")}, path)
        assert confarg.merge(WithPath, argv=[], env={}, files=[path]) == {"out": "sub/x.txt"}

    @pytest.mark.parametrize("suffix", [".toml", ".yaml", ".json"])
    def test_enum_leaf(self, tmp_path: Path, suffix: str) -> None:
        """An Enum dumps as its value, in every format."""
        WithEnum = make_target("color", Color, default=Color.RED)
        path = tmp_path / f"out{suffix}"
        confarg.dump_file({"color": Color.BLUE}, path)
        assert confarg.merge(WithEnum, argv=[], env={}, files=[path]) == {"color": "blue"}

    def test_coerced_leaf_inside_containers(self, tmp_path: Path) -> None:
        """Object leaves are converted wherever they sit, not only at the top level."""
        WithPaths = make_target("outs", list[Path], default_factory=list)
        path = tmp_path / "out.yaml"
        confarg.dump_file({"outs": [Path("a.txt"), Path("b.txt")]}, path)
        assert confarg.merge(WithPaths, argv=[], env={}, files=[path]) == {"outs": ["a.txt", "b.txt"]}

    @pytest.mark.parametrize(
        ("target", "argv", "env"),
        [
            (make_target("out", Path, default=Path("default.txt")), ["--out", "sub/x.txt"], {}),
            (make_target("color", Color, default=Color.RED), [], {"APP__COLOR": "blue"}),
        ],
        ids=["cli-path", "env-enum"],
    )
    def test_a_merged_dict_round_trips(self, tmp_path: Path, target: Any, argv: list[str], env: dict[str, str]) -> None:
        """A token stays as written, so the merged dict reads back from its dump unchanged (BUG-246)."""
        raw = confarg.merge(target, argv=argv, env=env, env_prefix="APP")
        path = tmp_path / "out.yaml"
        confarg.dump_file(raw, path)
        assert confarg.merge(target, argv=[], env={}, files=[path]) == raw


class TestDumpRawDictTokens:
    """No token type reaches a writer: every one of them is unwrapped to a plain ``str``.

    A lone CLI token for a scalar+sequence union is a ``_UnionSeqToken``, a *subclass*
    of ``_StrToken``, so the unwrap has to recognise the whole token hierarchy and not
    just its root — see docs-dev/architecture/invariants.md#tokens-mean-untyped-text.
    """

    @pytest.mark.parametrize("suffix", [".toml", ".yaml", ".json"])
    def test_union_seq_token_dumps_as_plain_str(self, tmp_path: Path, suffix: str) -> None:
        """``--input hello`` for ``bool | list[str]`` dumps as a string, in every format."""
        WithScalarOrList = make_target("input", Union[bool, list[str]], default=False)
        raw = confarg.merge(WithScalarOrList, argv=["--input", "hello"], env={})
        assert type(raw["input"]) is _UnionSeqToken

        path = tmp_path / f"out{suffix}"
        confarg.dump_file(raw, path)
        assert confarg.merge(WithScalarOrList, argv=[], env={}, files=[path]) == {"input": "hello"}

    def test_token_subclass_leaves_as_exactly_str(self) -> None:
        """The unwrap flattens the subclass, not only the base.

        JSON and TOML write a ``str`` subclass without complaint, so the format
        round trip above cannot see the leak on its own; the leaf serializer can.
        """
        assert type(_serialize_leaf(str, _UnionSeqToken("hello"))) is str
        assert type(_serialize_leaf(str, _StrToken("hello"))) is str

    def test_foreign_str_subclass_is_untouched(self) -> None:
        """Only confarg's own tokens are unwrapped; a caller's ``str`` subclass is not.

        ``_StrToken`` is private, so nothing a user writes inherits from it, and the
        registry loop below the unwrap stays reachable for a registered ``str`` leaf.
        """

        class _Tagged(str):
            __slots__ = ()

        value = _Tagged("hello")
        assert _serialize_leaf(str, value) is value


@_dc
class _CastInner:
    count: Union[int, str] = 0


@_dc
class _CastOuter:
    inner: _CastInner = field(default_factory=_CastInner)


class TestDumpRawDictForceCasts:
    """dump_file(raw_dict) writes a force-cast back in its file spelling.

    A ``.int``/``.str``/... suffix on the CLI stores a pin in the merged dict, and no
    writer accepts one. The pin is emitted as the ``{__cast__, __value__}`` dict a
    config file uses for the same purpose, so the cast survives the round trip instead
    of being flattened to a bare scalar an earlier union variant could steal back.
    """

    @pytest.mark.parametrize("suffix", [".toml", ".yaml", ".json"])
    def test_scalar_cast_dumps_as_the_file_spelling(self, tmp_path: Path, suffix: str) -> None:
        """``--count.int 5`` is written as ``{__cast__: int, __value__: "5"}``, in every format."""
        WithUnion = make_target("count", Union[int, str], default=0)
        raw = confarg.merge(WithUnion, argv=["--count.int", "5"], env={})
        assert raw["count"] == _Pinned(int, _StrToken("5"))

        path = tmp_path / f"out{suffix}"
        confarg.dump_file(raw, path)
        reloaded = confarg.merge(WithUnion, argv=[], env={}, files=[path])
        assert reloaded == {"count": {"__cast__": "int", "__value__": "5"}}
        assert confarg.build(WithUnion, raw) == confarg.build(WithUnion, reloaded)
        assert confarg.build(WithUnion, raw).count == 5

    def test_cast_value_is_a_plain_str(self) -> None:
        """The pinned token is unwrapped: no token type reaches a writer.

        ``__value__`` holds a ``_StrToken``, which the writers accept as a ``str``
        subclass without complaint, so only the serializer can see the leak.
        See docs-dev/architecture/invariants.md#tokens-mean-untyped-text.
        """
        out = _serialize_untyped({"count": _Pinned(int, _StrToken("5"))})
        assert type(out["count"]["__value__"]) is str

    def test_cast_inside_a_nested_struct(self, tmp_path: Path) -> None:
        """A pin is emitted wherever it sits, not only at the top level."""
        raw = confarg.merge(_CastOuter, argv=["--inner.count.int", "5"], env={})
        assert raw == {"inner": {"count": _Pinned(int, _StrToken("5"))}}

        path = tmp_path / "out.yaml"
        confarg.dump_file(raw, path)
        assert confarg.merge(_CastOuter, argv=[], env={}, files=[path]) == {
            "inner": {"count": {"__cast__": "int", "__value__": "5"}},
        }

    def test_file_spelling_re_dumps_unchanged(self, tmp_path: Path) -> None:
        """A cast that came from a file is already in its file spelling: dumping is idempotent."""
        WithUnion = make_target("count", Union[int, str], default=0)
        path = tmp_path / "in.json"
        path.write_text('{"count": {"__cast__": "int", "__value__": "5"}}', encoding="utf-8")
        raw = confarg.merge(WithUnion, argv=[], env={}, files=[path])

        out = tmp_path / "out.json"
        confarg.dump_file(raw, out)
        assert confarg.merge(WithUnion, argv=[], env={}, files=[out]) == raw

    def test_the_cast_still_wins_over_an_earlier_variant(self, tmp_path: Path) -> None:
        """Flattening the pin to its bare value would lose the round trip.

        ``Color | str`` reads a plain ``"red"`` back as ``Color.RED`` by declaration
        order, so writing the coerced value is only safe while the pin separates
        scalars. ``_serialize_untyped`` is type-blind and cannot tell the two apart,
        so it keeps the pin in every case.
        """
        WithColorOrStr = make_target("v", Union[Color, str], default=Color.RED)
        raw = confarg.merge(WithColorOrStr, argv=["--v.str", "red"], env={})
        assert confarg.build(WithColorOrStr, {"v": "red"}).v is Color.RED

        path = tmp_path / "out.yaml"
        confarg.dump_file(raw, path)
        reloaded = confarg.merge(WithColorOrStr, argv=[], env={}, files=[path])
        assert confarg.build(WithColorOrStr, raw) == confarg.build(WithColorOrStr, reloaded)
        assert confarg.build(WithColorOrStr, reloaded).v == "red"


# ---------------------------------------------------------------------------
# Registered leaf types
# ---------------------------------------------------------------------------


class _Version:
    """A registered leaf type whose ``str()`` is *not* its wire form."""

    def __init__(self, major: int, minor: int) -> None:
        self.major = major
        self.minor = minor

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Version) and (self.major, self.minor) == (other.major, other.minor)

    def __hash__(self) -> int:
        return hash((self.major, self.minor))

    def __str__(self) -> str:
        return f"<Version {self.major}.{self.minor}>"


def _coerce_version(value: object) -> _Version:
    major, minor = str(value).split(".")
    return _Version(int(major), int(minor))


_UUID_TEXT = "12345678-1234-5678-1234-567812345678"


@pytest.mark.usefixtures("leaf_registry")
class TestDumpRegisteredLeafTypes:
    """A type registered with register_leaf_type is a leaf on the way out too.

    Registration makes a type a leaf on the way in even when it looks like a
    struct; serialization must mirror that, or ``dump()`` emits the type's
    fields and ``dump_file()`` hands the writers an object they cannot
    represent.
    """

    def test_dump_instance(self) -> None:
        """dump() emits the scalar form, not the type's attributes."""
        confarg.register_leaf_type(UUID, UUID)
        WithUuid = make_target("id", UUID, default=UUID(int=0))
        assert confarg.dump(WithUuid(id=UUID(_UUID_TEXT))) == {"id": _UUID_TEXT}

    @pytest.mark.parametrize("suffix", [".toml", ".yaml", ".json"])
    def test_dump_file_from_raw_dict(self, tmp_path: Path, suffix: str) -> None:
        """A registered leaf a dict holds is written as a scalar, in every format."""
        confarg.register_leaf_type(UUID, UUID)
        WithUuid = make_target("id", UUID, default=UUID(int=0))
        raw = {"id": UUID(_UUID_TEXT)}

        path = tmp_path / f"out{suffix}"
        confarg.dump_file(raw, path)
        reloaded = confarg.merge(WithUuid, argv=[], env={}, files=[path])
        assert reloaded == {"id": _UUID_TEXT}
        assert confarg.build(WithUuid, raw) == confarg.build(WithUuid, reloaded)

    def test_dump_file_from_instance(self, tmp_path: Path) -> None:
        """The typed path round-trips through a file as well."""
        confarg.register_leaf_type(UUID, UUID)
        WithUuid = make_target("id", UUID, default=UUID(int=0))
        path = tmp_path / "out.yaml"
        confarg.dump_file(WithUuid(id=UUID(_UUID_TEXT)), path)
        assert confarg.load(WithUuid, argv=[], env={}, files=[path]) == WithUuid(id=UUID(_UUID_TEXT))

    def test_inside_containers(self, tmp_path: Path) -> None:
        """Registered leaves are converted wherever they sit, not only at the top level."""
        confarg.register_leaf_type(UUID, UUID)
        WithUuids = make_target("ids", list[UUID], default_factory=list)
        raw = confarg.merge(WithUuids, argv=["--ids", _UUID_TEXT], env={})

        path = tmp_path / "out.yaml"
        confarg.dump_file(raw, path)
        assert confarg.merge(WithUuids, argv=[], env={}, files=[path]) == {"ids": [_UUID_TEXT]}

    def test_as_dict_value_and_key(self) -> None:
        """A registered leaf serializes as a dict value and as a dict key."""
        confarg.register_leaf_type(UUID, UUID)
        WithMap = make_target("ids", dict[UUID, UUID], default_factory=dict)
        dumped = confarg.dump(WithMap(ids={UUID(_UUID_TEXT): UUID(int=0)}))
        assert dumped == {"ids": {_UUID_TEXT: str(UUID(int=0))}}

    def test_optional(self) -> None:
        """A registered leaf in a union is serialized through its variant."""
        confarg.register_leaf_type(UUID, UUID)
        WithOptional = make_target("id", Union[UUID, None], default=None)
        assert confarg.dump(WithOptional(id=UUID(_UUID_TEXT))) == {"id": _UUID_TEXT}
        assert confarg.dump(WithOptional(id=None)) == {"id": None}

    def test_serialize_hook_is_used(self, tmp_path: Path) -> None:
        """An explicit serialize= callable replaces the str() default, on both paths."""
        confarg.register_leaf_type(_Version, _coerce_version, serialize=lambda v: f"{v.major}.{v.minor}")
        WithVersion = make_target("v", _Version, default=_Version(0, 0))

        assert confarg.dump(WithVersion(v=_Version(1, 2))) == {"v": "1.2"}

        path = tmp_path / "out.yaml"
        confarg.dump_file(confarg.merge(WithVersion, argv=["--v", "1.2"], env={}), path)
        assert confarg.merge(WithVersion, argv=[], env={}, files=[path]) == {"v": "1.2"}

    @pytest.mark.parametrize("suffix", [".toml", ".yaml", ".json"])
    def test_serialize_hook_may_return_a_non_string(self, tmp_path: Path, suffix: str) -> None:
        """A serializer returning a native scalar keeps that type in the file."""
        confarg.register_leaf_type(_Version, _coerce_version, serialize=lambda v: v.major)
        WithVersion = make_target("v", _Version, default=_Version(0, 0))

        path = tmp_path / f"out{suffix}"
        confarg.dump_file(WithVersion(v=_Version(7, 0)), path)
        assert confarg.merge(WithVersion, argv=[], env={}, files=[path]) == {"v": 7}

    def test_serialize_defaults_to_str(self) -> None:
        """Omitting serialize= falls back to str(), warts and all."""
        confarg.register_leaf_type(_Version, _coerce_version)
        WithVersion = make_target("v", _Version, default=_Version(0, 0))
        assert confarg.dump(WithVersion(v=_Version(1, 2))) == {"v": "<Version 1.2>"}

    def test_struct_union_is_not_tagged(self) -> None:
        """A registered leaf is not a second struct variant, so no tag is emitted.

        ``UUID`` is a struct by introspection and its ``__init__`` takes a
        ``version``, so ``_needs_tag`` used to see two candidates for a
        ``Release | UUID`` field and tag a union with only one struct in it.
        """
        confarg.register_leaf_type(UUID, UUID)
        WithRelease = make_target("v", Union[Release, UUID], default_factory=Release)
        assert confarg.dump(WithRelease(v=Release(version=2))) == {"v": {"version": 2}}

    def test_struct_union_round_trips_untagged(self) -> None:
        """Both variants survive dump() -> build() with no tag in between."""
        confarg.register_leaf_type(UUID, UUID)
        WithRelease = make_target("v", Union[Release, UUID], default_factory=Release)
        for value in (Release(version=2), UUID(_UUID_TEXT)):
            instance = WithRelease(v=value)
            assert confarg.build(WithRelease, confarg.dump(instance)) == instance

    def test_struct_union_still_tagged_when_policy_is_always(self) -> None:
        """tag_policy="always" is unaffected: the one struct variant is still tagged."""
        confarg.register_leaf_type(UUID, UUID)
        WithRelease = make_target("v", Union[Release, UUID], default_factory=Release)
        dumped = confarg.dump(WithRelease(v=Release(version=2)), tag_policy="always")
        assert dumped == {"v": {"version": 2, "class": "tests.conftest.Release"}}


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestDumpErrors:
    """Error handling for dump()."""

    def test_not_a_dataclass(self) -> None:
        """Test that passing a non-dataclass to dump raises TypeError."""
        with pytest.raises(TypeError, match="instance"):
            confarg.dump("not a dataclass")

    def test_dataclass_class_not_instance(self) -> None:
        """Test that passing a dataclass class (not instance) to dump raises TypeError."""
        with pytest.raises(TypeError, match="instance"):
            confarg.dump(Flat)


# ---------------------------------------------------------------------------
# Line endings
# ---------------------------------------------------------------------------


class TestDumpLineEndings:
    """dump_file writes LF-only files on every platform."""

    @pytest.mark.parametrize("suffix", [".toml", ".yaml", ".json"])
    def test_no_carriage_returns(self, tmp_path: Path, suffix: str) -> None:
        """Dumped config files never contain CR, so output is byte-identical across platforms."""
        obj = AppConfig(
            db=DbConfig(host="localhost", port=5432, name="mydb"),
            cache=CacheConfig(enabled=True, ttl=600),
            debug=True,
        )
        path = tmp_path / f"out{suffix}"
        confarg.dump_file(obj, path)
        assert b"\r" not in path.read_bytes()


@_dc
class _FinalInner:
    x: int = 1


@_dc
class _WithFinalStruct:
    inner: Final[_FinalInner] = field(default_factory=_FinalInner)


class TestFinalRoundTrip:
    """A ``Final[Struct]`` field builds from and dumps to a dict, as the bare struct does."""

    def test_builds_from_dict(self) -> None:
        """The struct inside ``Final`` is built from its fields."""
        assert confarg.from_dict(_WithFinalStruct, {"inner": {"x": 5}}) == _WithFinalStruct(_FinalInner(5))

    def test_dumps_to_dict(self) -> None:
        """The struct inside ``Final`` is dumped field by field, not passed through."""
        assert confarg.dump(_WithFinalStruct(_FinalInner(5))) == {"inner": {"x": 5}}


@_dc
class _WithReservedKeys:
    d: dict[str, int] = field(default_factory=dict)
    nested: dict[str, dict[str, int]] = field(default_factory=dict)
    anything: Any = None


class TestDumpRefusesAReservedDataKey:
    """A data key named like a reserved key would be read back as the file's own, so ``dump()`` refuses it (BUG-241)."""

    @pytest.mark.parametrize("key", sorted(confarg._defaults.RESERVED_KEYS))
    def test_a_dict_fields_key(self, key: str) -> None:
        """The refusal names the key's path, as argv and the environment refuse the key on theirs."""
        with pytest.raises(ConfargError, match=re.escape(f"Cannot dump the key {key!r} at 'd.{key}'")):
            confarg.dump(_WithReservedKeys(d={key: 1}))

    @pytest.mark.parametrize(
        ("cfg", "path"),
        [
            pytest.param(_WithReservedKeys(nested={"x": {"__include__": 1}}), "nested.x.__include__", id="nested-dict"),
            pytest.param(_WithReservedKeys(anything={"__cast__": "int"}), "anything.__cast__", id="any"),
            pytest.param(_WithReservedKeys(anything=[{"__root__": 1}]), "anything[0].__root__", id="any-in-a-list"),
        ],
    )
    def test_at_any_depth(self, cfg: _WithReservedKeys, path: str) -> None:
        """Below a dict, inside an ``Any``, in a list: wherever a file would read the key."""
        with pytest.raises(ConfargError, match=re.escape(f"at '{path}'")):
            confarg.dump(cfg)

    def test_dump_file_of_an_instance_refuses_it(self, tmp_path: Path) -> None:
        """``dump_file`` writes an instance as ``dump()`` serializes it."""
        with pytest.raises(ConfargError, match="Cannot dump the key '__append__'"):
            confarg.dump_file(_WithReservedKeys(d={"__append__": 1}), tmp_path / "out.yaml")

    def test_dump_file_of_a_raw_dict_writes_the_key_as_the_op(self, tmp_path: Path) -> None:
        """A raw dict is a document: its ``__append__`` is the op, as a file reads it."""
        out = tmp_path / "out.yaml"
        confarg.dump_file({"nested": {"x": {"__append__": [1]}}}, out)
        assert confarg.merge(_WithReservedKeys, argv=[], env={}, files=[out]) == {
            "nested": {"x": {confarg.ListOp.APPEND: [1]}},
        }

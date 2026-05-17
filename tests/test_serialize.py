# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for serialization: dump(), dump_file()."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass as _dc
from pathlib import Path
from typing import Literal, Union
from unittest import mock

import pytest

import confarg
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
            (_DL_WithPath(location=Path("/tmp/foo")), "location", str(Path("/tmp/foo"))),
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


class TestDumpSubclass:
    """Serialization of dataclass subclasses held via a base-class field."""

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

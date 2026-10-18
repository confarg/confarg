# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for composite types: dataclass, list, tuple, set, frozenset, dict, Union, Optional, nesting."""

from __future__ import annotations

import collections
import enum
import re
from dataclasses import dataclass
from typing import Any, Optional, TypedDict, Union

import pytest

import confarg
from confarg.exceptions import ConfargWarning, TypeCoercionError
from tests.conftest import (
    AppConfig,
    BoolVariantA,
    CircleShape,
    DbConfig,
    DeepNested,
    FloatHolder,
    MultiVal,
    PgConfig,
    RectangleShape,
    RedisConfig,
    ServerTcp,
    ServerUnix,
    SingleVal,
    SqlBackend,
    SqlCredentials,
    SquareShape,
    StrHolder,
    TaggedBool,
    TaggedStr,
    TokenBackend,
    TokenCredentials,
    TypedVariantA,
    TypedVariantB,
    WithAgreedBoolUnion,
    WithCollectionOrScalar,
    WithCollections,
    WithNestedList,
    WithOptionalNested,
    WithTaggedUnion,
    WithTypeLiteralUnion,
    WithUnionAmbiguous,
    WithUnionAmbiguousThree,
    WithUnionDeepDisambiguation,
    WithUnionDisjointDefaults,
    WithUnionFloatStr,
    WithUnionNested,
    WithUnionOverlap,
    make_target,
)

# ---------------------------------------------------------------------------
# Duplicate-name collision fixtures (two classes named "CircleShape" in
# different modules, used for fully-qualified tag tests)
# ---------------------------------------------------------------------------


@dataclass
class _CircleShapeOther:
    x: float
    y: float
    radius: float


# Simulate a class from a different module with the same short name.
_CircleShapeOther.__name__ = "CircleShape"
_CircleShapeOther.__qualname__ = "CircleShape"
_CircleShapeOther.__module__ = "other.shapes"


@dataclass
class WithDuplicateNameUnion:
    """Union of two CircleShape variants from different modules (same short name)."""

    shape: CircleShape | _CircleShapeOther


# ---------------------------------------------------------------------------
# Nested dataclass
# ---------------------------------------------------------------------------


class TestNestedDataclass:
    """Nested dataclass composition."""

    def test_nested_from_cli(self) -> None:
        """Parse nested dataclass fields via dot-separated CLI args."""
        result = confarg.load(
            AppConfig,
            argv=["--db.host", "localhost", "--db.port", "5432", "--db.name", "mydb"],
            env={},
        )
        assert result.db.host == "localhost"
        assert result.db.port == 5432
        assert result.db.name == "mydb"

    def test_nested_defaults_applied(self) -> None:
        """Nested dataclass fields with defaults are optional."""
        result = confarg.load(
            AppConfig,
            argv=["--db.host", "localhost", "--db.port", "5432", "--db.name", "mydb"],
            env={},
        )
        assert result.cache.enabled is True
        assert result.cache.ttl == 300
        assert result.debug is False

    def test_deep_nested_from_cli(self) -> None:
        """Three levels of nesting via CLI."""
        result = confarg.load(
            DeepNested,
            argv=[
                "--app.db.host",
                "h",
                "--app.db.port",
                "1",
                "--app.db.name",
                "n",
            ],
            env={},
        )
        assert result.app.db.host == "h"
        assert result.version == "1.0"


# ---------------------------------------------------------------------------
# Collections: list, tuple, set, frozenset, dict
# ---------------------------------------------------------------------------


class TestCollections:
    """Parametrized collection type parsing."""

    @pytest.mark.parametrize(
        ("target_cls", "args", "field", "expected"),
        [
            (
                make_target("items", list[int], default_factory=list),
                ["--items", "1", "2", "3"],
                "items",
                [1, 2, 3],
            ),
            (
                make_target("items", list[int], default_factory=list),
                ["--items.0", "10", "--items.1", "20"],
                "items",
                [10, 20],
            ),
            (
                make_target("tags", set[str], default_factory=set),
                ["--tags", "a", "b", "c"],
                "tags",
                {"a", "b", "c"},
            ),
            (
                make_target("tags", frozenset[str], default_factory=frozenset),
                ["--tags", "x", "y"],
                "tags",
                frozenset({"x", "y"}),
            ),
            (
                make_target("pair", tuple[str, int], default=("", 0)),
                ["--pair", "hello", "42"],
                "pair",
                ("hello", 42),
            ),
        ],
        ids=[
            "list-space-separated",
            "list-indexed",
            "set-space-separated",
            "frozenset-space-separated",
            "tuple-positional",
        ],
    )
    def test_collection_from_cli(self, target_cls, args, field, expected) -> None:
        """Parse various collection types from CLI."""
        result = confarg.load(target_cls, argv=args, env={})
        assert getattr(result, field) == expected

    def test_list_empty_default(self) -> None:
        """Empty list default preserved when no input."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, argv=[], env={})
        assert result.items == []

    def test_list_from_env_indexed(self) -> None:
        """Parse a list from indexed env vars."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(
            WithList,
            argv=[],
            env={"MYAPP_ITEMS__0": "5", "MYAPP_ITEMS__1": "6"},
            env_prefix="MYAPP_",
        )
        assert result.items == [5, 6]

    def test_set_deduplication(self) -> None:
        """Set deduplicates input values."""
        WithSet = make_target("tags", set[str], default_factory=set)
        result = confarg.load(WithSet, argv=["--tags", "a", "a", "b"], env={})
        assert result.tags == {"a", "b"}

    def test_tuple_default(self) -> None:
        """Tuple default preserved when no input."""
        WithTuple = make_target("pair", tuple[str, int], default=("", 0))
        result = confarg.load(WithTuple, argv=[], env={})
        assert result.pair == ("", 0)

    @pytest.mark.parametrize(
        ("field_type", "default_factory", "value", "expected"),
        [
            (list, list, [1, "a"], [1, "a"]),
            (set, set, [1, 2], {1, 2}),
            (frozenset, frozenset, [1, 2], frozenset({1, 2})),
            (tuple, tuple, ["a", 1], ("a", 1)),
        ],
        ids=["list", "set", "frozenset", "tuple"],
    )
    def test_bare_collection_builds(self, field_type, default_factory, value, expected) -> None:
        """A bare collection annotation builds, as its Any-parameterized form does (BUG-211)."""
        WithCollection = make_target("items", field_type, default_factory=default_factory)
        result = confarg.build(WithCollection, {"items": value})
        assert result.items == expected

    def test_bare_list_from_cli(self) -> None:
        """A bare list field takes space-separated tokens, as list[Any] does (BUG-211)."""
        WithList = make_target("items", list, default_factory=list)
        result = confarg.load(WithList, argv=["--items", "a", "b"], env={})
        assert result.items == ["a", "b"]

    def test_bare_tuple_from_cli_is_variadic(self) -> None:
        """A bare tuple is a variadic tuple, not a fixed zero-length one (BUG-211)."""
        WithTuple = make_target("pair", tuple, default=())
        result = confarg.load(WithTuple, argv=["--pair", "a", "b"], env={})
        assert result.pair == ("a", "b")


class TestDict:
    """Dict type parsing."""

    def test_dict_from_cli_key_value(self) -> None:
        """Parse a dict from indexed CLI args."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        result = confarg.load(
            WithDict,
            argv=["--metadata.alpha", "1", "--metadata.beta", "2"],
            env={},
        )
        assert result.metadata == {"alpha": 1, "beta": 2}

    def test_dict_from_env(self) -> None:
        """Parse a dict from env vars."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        result = confarg.load(
            WithDict,
            argv=[],
            env={"MYAPP_METADATA__foo": "10", "MYAPP_METADATA__bar": "20"},
            env_prefix="MYAPP_",
        )
        assert result.metadata == {"foo": 10, "bar": 20}

    def test_dict_empty_default(self) -> None:
        """Empty dict default preserved when no input."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        result = confarg.load(WithDict, argv=[], env={})
        assert result.metadata == {}

    def test_bare_dict_builds_from_a_mapping(self) -> None:
        """A field annotated with the bare dict builds, as dict[Any, Any] should (BUG-187)."""
        WithDict = make_target("metadata", dict, default_factory=dict)
        result = confarg.build(WithDict, {"metadata": {"x": 1}})
        assert result.metadata == {"x": 1}

    def test_bare_dict_keeps_non_string_keys(self) -> None:
        """The bare dict's keys are Any, so a file's non-string keys stay as written (BUG-187)."""
        WithDict = make_target("metadata", dict, default_factory=dict)
        result = confarg.build(WithDict, {"metadata": {1: "a", "b": 2}})
        assert result.metadata == {1: "a", "b": 2}

    def test_bare_dict_from_cli_key_value(self) -> None:
        """A bare dict field takes subkey flags, as a typed dict field does (BUG-187)."""
        WithDict = make_target("metadata", dict, default_factory=dict)
        result = confarg.load(WithDict, argv=["--metadata.alpha", "1", "--metadata.beta", "2"], env={})
        assert result.metadata == {"alpha": "1", "beta": "2"}

    def test_bare_dict_from_env(self) -> None:
        """A bare dict field takes env-var keys, as a typed dict field does (BUG-187)."""
        WithDict = make_target("metadata", dict, default_factory=dict)
        result = confarg.load(
            WithDict,
            argv=[],
            env={"MYAPP_METADATA__foo": "10", "MYAPP_METADATA__bar": "20"},
            env_prefix="MYAPP_",
        )
        assert result.metadata == {"foo": "10", "bar": "20"}

    def test_dict_any_keys_build(self) -> None:
        """dict[Any, K] builds: an Any key passes through, native or token alike (BUG-212)."""
        WithDict = make_target("metadata", dict[Any, int], default_factory=dict)
        result = confarg.build(WithDict, {"metadata": {"x": 1, 2: 3}})
        assert result.metadata == {"x": 1, 2: 3}

    def test_bare_dict_dump_roundtrip(self) -> None:
        """A bare dict field dumps and loads back, as a typed dict field does (BUG-187)."""
        WithDict = make_target("metadata", dict, default_factory=dict)
        built = confarg.build(WithDict, {"metadata": {"x": 1}})
        assert confarg.dump(built) == {"metadata": {"x": 1}}

    def test_dict_union_value_with_nested_dict(self) -> None:
        """Dict value type that is a union containing a dict variant constructs correctly."""

        @dataclass
        class Cfg:
            foo: dict[str, int | str | dict[str, int]]

        result = confarg.build(
            Cfg,
            {"foo": {"hello": 42, "baz": "1", "qux": {"quxx": -1}}},
        )
        assert result.foo == {"hello": 42, "baz": "1", "qux": {"quxx": -1}}
        assert isinstance(result.foo["qux"], dict)

    def test_dict_union_value_with_list(self) -> None:
        """Dict value type that is a union containing a list variant constructs correctly."""

        @dataclass
        class Cfg:
            data: dict[str, int | list[int]]

        result = confarg.build(
            Cfg,
            {"data": {"count": 5, "ids": [1, 2, 3]}},
        )
        assert result.data == {"count": 5, "ids": [1, 2, 3]}
        assert isinstance(result.data["ids"], list)


# ---------------------------------------------------------------------------
# Union / Optional
# ---------------------------------------------------------------------------


class TestUnion:
    """Union type parsing."""

    @pytest.mark.parametrize(
        ("args", "expected", "expected_type"),
        [
            (["--value", "42"], 42, int),
            (["--value", "hello"], "hello", str),
        ],
        ids=["int-variant", "str-variant"],
    )
    def test_union_int_str(self, args, expected, expected_type) -> None:
        """Union[int, str] picks correct variant based on input."""
        WithUnion = make_target("value", Union[int, str], default=0)
        result = confarg.load(WithUnion, argv=args, env={})
        assert result.value == expected
        assert isinstance(result.value, expected_type)

    @pytest.mark.parametrize(
        ("target_cls", "args", "expected"),
        [
            (make_target("value", Optional[int], default=None), [], None),
            (make_target("value", Optional[int], default=None), ["--value", "7"], 7),
            (make_target("value", int | None, default=None), [], None),
            (make_target("value", int | None, default=None), ["--value", "7"], 7),
        ],
        ids=[
            "Optional-none",
            "Optional-provided",
            "pipe-none-none",
            "pipe-none-provided",
        ],
    )
    def test_optional(self, target_cls, args, expected) -> None:
        """Optional/pipe-none fields default to None or parse value."""
        result = confarg.load(target_cls, argv=args, env={})
        assert result.value == expected


# ---------------------------------------------------------------------------
# Union edge cases — leaf disambiguation
# ---------------------------------------------------------------------------


class TestUnionLeafDisambiguation:
    """Leaf union disambiguation: int vs float, bool vs int, three-way.

    The rank is ``int > float > bool``, so ``Union[int, float]`` takes an integral token as an
    int and any other number as a float, and ``Union[bool, int]`` takes a numeric one as an int.
    """

    @pytest.mark.parametrize(
        ("target_cls", "source", "expected", "expected_type"),
        [
            # int vs float — int outranks float, so only an integral token lands on int
            (make_target("value", Union[int, float], default=0), {"args": ["--value", "42"]}, 42, int),
            (make_target("value", Union[int, float], default=0), {"args": ["--value", "3.14"]}, 3.14, float),
            # bool vs int
            (make_target("value", Union[bool, int], default=0), {"env": {"MYAPP_VALUE": "true"}}, True, bool),
            (make_target("value", Union[bool, int], default=0), {"env": {"MYAPP_VALUE": "false"}}, False, bool),
            (make_target("value", Union[bool, int], default=0), {"args": ["--value", "42"]}, 42, int),
            # three-way
            (make_target("value", Union[int, float, str], default=0), {"args": ["--value", "7"]}, 7, int),
            (make_target("value", Union[int, float, str], default=0), {"args": ["--value", "1.5"]}, 1.5, float),
            (make_target("value", Union[int, float, str], default=0), {"args": ["--value", "hello"]}, "hello", str),
        ],
        ids=[
            "int-float-int",
            "int-float-float",
            "bool-int-true",
            "bool-int-false",
            "bool-int-numeric",
            "three-int",
            "three-float",
            "three-str",
        ],
    )
    def test_leaf_disambiguation(self, target_cls, source, expected, expected_type) -> None:
        """Leaf union types disambiguate by the stealing rule, not by declaration order."""
        args = source.get("args", [])
        env = source.get("env", {})
        result = confarg.load(target_cls, argv=args, env=env, env_prefix="MYAPP_")
        assert result.value == expected
        assert isinstance(result.value, expected_type)


# ---------------------------------------------------------------------------
# Union edge cases — dataclass disambiguation
# ---------------------------------------------------------------------------


class TestUnionEdgeCases:
    """Edge cases for Union type resolution with dataclasses."""

    def test_union_overlapping_field_int_port_cli_ambiguous(self) -> None:
        """Union[ServerTcp, ServerUnix]: CLI numeric port is ambiguous."""
        with pytest.raises(confarg.exceptions.AmbiguousUnionError):
            confarg.load(
                WithUnionOverlap,
                argv=["--server.host", "localhost", "--server.port", "5432"],
                env={},
            )

    def test_union_overlapping_field_str_port(self) -> None:
        """Union[ServerTcp, ServerUnix]: non-numeric port disambiguates to ServerUnix."""
        result = confarg.load(
            WithUnionOverlap,
            argv=["--server.host", "localhost", "--server.port", "/var/run/pg.sock"],
            env={},
        )
        assert isinstance(result.server, ServerUnix)
        assert result.server.port == "/var/run/pg.sock"

    def test_union_overlapping_from_toml_int(self, tmp_toml) -> None:
        """TOML with integer port resolves to ServerTcp."""
        path = tmp_toml("""\
            [server]
            host = "localhost"
            port = 5432
        """)
        result = confarg.load(WithUnionOverlap, argv=[], env={}, files=[path])
        assert isinstance(result.server, ServerTcp)
        assert result.server.port == 5432

    def test_union_overlapping_from_toml_str(self, tmp_toml) -> None:
        """TOML with string port resolves to ServerUnix."""
        path = tmp_toml("""\
            [server]
            host = "localhost"
            port = "/var/run/pg.sock"
        """)
        result = confarg.load(WithUnionOverlap, argv=[], env={}, files=[path])
        assert isinstance(result.server, ServerUnix)
        assert result.server.port == "/var/run/pg.sock"

    def test_union_disjoint_defaults_pg(self) -> None:
        """Union[PgConfig, RedisConfig]: sslmode field disambiguates to PgConfig."""
        result = confarg.load(
            WithUnionDisjointDefaults,
            argv=[
                "--backend.host",
                "h",
                "--backend.port",
                "5432",
                "--backend.sslmode",
                "require",
            ],
            env={},
        )
        assert isinstance(result.backend, PgConfig)
        assert result.backend.sslmode == "require"

    def test_union_disjoint_defaults_redis(self) -> None:
        """Union[PgConfig, RedisConfig]: db field disambiguates to RedisConfig."""
        result = confarg.load(
            WithUnionDisjointDefaults,
            argv=[
                "--backend.host",
                "h",
                "--backend.port",
                "6379",
                "--backend.db",
                "1",
            ],
            env={},
        )
        assert isinstance(result.backend, RedisConfig)
        assert result.backend.db == 1

    def test_union_nested_int_or_dataclass_int(self) -> None:
        """Union[int, DbConfig]: plain int value resolves to int."""
        result = confarg.load(WithUnionNested, argv=["--value", "42"], env={})
        assert result.value == 42

    def test_union_nested_int_or_dataclass_dataclass(self) -> None:
        """Union[int, DbConfig]: subfields resolve to DbConfig."""
        result = confarg.load(
            WithUnionNested,
            argv=["--value.host", "h", "--value.port", "1", "--value.name", "n"],
            env={},
        )
        assert isinstance(result.value, DbConfig)
        assert result.value.host == "h"

    def test_union_deep_disambiguation_sql_cli(self) -> None:
        """Union[SqlBackend, TokenBackend]: auth.username disambiguates to SqlBackend."""
        result = confarg.load(
            WithUnionDeepDisambiguation,
            argv=[
                "--backend.host",
                "db.example.com",
                "--backend.auth.username",
                "admin",
                "--backend.auth.password",
                "secret",
            ],
            env={},
        )
        assert isinstance(result.backend, SqlBackend)
        assert isinstance(result.backend.auth, SqlCredentials)
        assert result.backend.auth.username == "admin"

    def test_union_deep_disambiguation_token_cli(self) -> None:
        """Union[SqlBackend, TokenBackend]: auth.token disambiguates to TokenBackend."""
        result = confarg.load(
            WithUnionDeepDisambiguation,
            argv=[
                "--backend.host",
                "api.example.com",
                "--backend.auth.token",
                "abc123",
                "--backend.auth.expires",
                "3600",
            ],
            env={},
        )
        assert isinstance(result.backend, TokenBackend)
        assert isinstance(result.backend.auth, TokenCredentials)
        assert result.backend.auth.token == "abc123"
        assert result.backend.auth.expires == 3600

    def test_union_deep_disambiguation_sql_env(self) -> None:
        """Union[SqlBackend, TokenBackend]: env auth fields disambiguate to SqlBackend."""
        result = confarg.load(
            WithUnionDeepDisambiguation,
            argv=[],
            env={
                "MYAPP_BACKEND__HOST": "db.example.com",
                "MYAPP_BACKEND__AUTH__USERNAME": "admin",
                "MYAPP_BACKEND__AUTH__PASSWORD": "secret",
            },
            env_prefix="MYAPP_",
        )
        assert isinstance(result.backend, SqlBackend)
        assert result.backend.auth.username == "admin"

    def test_union_deep_disambiguation_token_env(self) -> None:
        """Union[SqlBackend, TokenBackend]: env auth fields disambiguate to TokenBackend."""
        result = confarg.load(
            WithUnionDeepDisambiguation,
            argv=[],
            env={
                "MYAPP_BACKEND__HOST": "api.example.com",
                "MYAPP_BACKEND__AUTH__TOKEN": "xyz",
                "MYAPP_BACKEND__AUTH__EXPIRES": "7200",
            },
            env_prefix="MYAPP_",
        )
        assert isinstance(result.backend, TokenBackend)
        assert result.backend.auth.token == "xyz"

    def test_union_deep_disambiguation_sql_toml(self, tmp_toml) -> None:
        """Union[SqlBackend, TokenBackend]: TOML with auth.username -> SqlBackend."""
        path = tmp_toml("""\
            [backend]
            host = "db.example.com"

            [backend.auth]
            username = "admin"
            password = "secret"
        """)
        result = confarg.load(WithUnionDeepDisambiguation, argv=[], env={}, files=[path])
        assert isinstance(result.backend, SqlBackend)
        assert result.backend.auth.password == "secret"

    def test_union_deep_disambiguation_token_toml(self, tmp_toml) -> None:
        """Union[SqlBackend, TokenBackend]: TOML with auth.token -> TokenBackend."""
        path = tmp_toml("""\
            [backend]
            host = "api.example.com"

            [backend.auth]
            token = "abc"
            expires = 1800
        """)
        result = confarg.load(WithUnionDeepDisambiguation, argv=[], env={}, files=[path])
        assert isinstance(result.backend, TokenBackend)
        assert result.backend.auth.expires == 1800

    def test_union_overlapping_cli_int_vs_str_ambiguous(self) -> None:
        """CLI numeric port matches both int and str variants -> AmbiguousUnionError."""
        with pytest.raises(confarg.exceptions.AmbiguousUnionError):
            confarg.load(
                WithUnionOverlap,
                argv=["--server.host", "h", "--server.port", "5432"],
                env={},
            )

    def test_union_overlapping_cli_class_tag_resolves(self) -> None:
        """Class tag resolves int-vs-str ambiguity for CLI numeric port."""
        result = confarg.load(
            WithUnionOverlap,
            argv=[
                "--server.class",
                "tests.conftest.ServerTcp",
                "--server.host",
                "h",
                "--server.port",
                "5432",
            ],
            env={},
        )
        assert isinstance(result.server, ServerTcp)
        assert result.server.port == 5432

    def test_union_overlapping_cli_str_only_not_ambiguous(self) -> None:
        """CLI non-numeric port matches only ServerUnix (str) -> no ambiguity."""
        result = confarg.load(
            WithUnionOverlap,
            argv=["--server.host", "h", "--server.port", "/var/run/pg.sock"],
            env={},
        )
        assert isinstance(result.server, ServerUnix)
        assert result.server.port == "/var/run/pg.sock"

    def test_union_overlapping_toml_native_int_not_ambiguous(self, tmp_toml) -> None:
        """TOML native int port resolves to ServerTcp without class tag."""
        path = tmp_toml("""\
            [server]
            host = "h"
            port = 5432
        """)
        result = confarg.load(WithUnionOverlap, argv=[], env={}, files=[path])
        assert isinstance(result.server, ServerTcp)
        assert result.server.port == 5432


# ---------------------------------------------------------------------------
# Union class tag disambiguation
# ---------------------------------------------------------------------------


class TestUnionClassTag:
    """Explicit class tag for disambiguating structurally identical Union members."""

    # --- CLI and Env ---

    @pytest.mark.parametrize(
        ("args", "env", "expected_cls", "expected_radius"),
        [
            (
                [
                    "--shape.class",
                    "tests.conftest.CircleShape",
                    "--shape.x",
                    "1",
                    "--shape.y",
                    "2",
                    "--shape.radius",
                    "5",
                ],
                {},
                CircleShape,
                5.0,
            ),
            (
                [
                    "--shape.class",
                    "tests.conftest.SquareShape",
                    "--shape.x",
                    "0",
                    "--shape.y",
                    "0",
                    "--shape.radius",
                    "3",
                ],
                {},
                SquareShape,
                3.0,
            ),
            (
                [],
                {
                    "MYAPP_SHAPE__CLASS": "tests.conftest.CircleShape",
                    "MYAPP_SHAPE__X": "1",
                    "MYAPP_SHAPE__Y": "2",
                    "MYAPP_SHAPE__RADIUS": "5",
                },
                CircleShape,
                5.0,
            ),
            (
                [],
                {
                    "MYAPP_SHAPE__CLASS": "tests.conftest.SquareShape",
                    "MYAPP_SHAPE__X": "0",
                    "MYAPP_SHAPE__Y": "0",
                    "MYAPP_SHAPE__RADIUS": "3",
                },
                SquareShape,
                3.0,
            ),
        ],
        ids=["cli-circle", "cli-square", "env-circle", "env-square"],
    )
    def test_tag_cli_env(self, args, env, expected_cls, expected_radius) -> None:
        """Test class tag via CLI and env resolves to the correct union variant."""
        result = confarg.load(WithUnionAmbiguous, argv=args, env=env, env_prefix="MYAPP_")
        assert isinstance(result.shape, expected_cls)
        assert result.shape.radius == expected_radius

    # --- Config files ---

    @pytest.mark.parametrize(
        ("class_path", "expected_cls", "radius"),
        [
            ("tests.conftest.CircleShape", CircleShape, 5.0),
            ("tests.conftest.SquareShape", SquareShape, 3.0),
        ],
        ids=["circle", "square"],
    )
    def test_tag_toml(self, tmp_toml, class_path, expected_cls, radius) -> None:
        """Test class tag in TOML resolves to the correct union variant."""
        path = tmp_toml(f'[shape]\nclass = "{class_path}"\nx = 1.0\ny = 2.0\nradius = {radius}\n')
        result = confarg.load(WithUnionAmbiguous, argv=[], env={}, files=[path])
        assert isinstance(result.shape, expected_cls)
        assert result.shape.radius == radius

    def test_tag_yaml_circle(self, tmp_yaml) -> None:
        """YAML class: tests.conftest.CircleShape selects CircleShape."""
        path = tmp_yaml("""\
            shape:
              class: tests.conftest.CircleShape
              x: 1.0
              y: 2.0
              radius: 5.0
        """)
        result = confarg.load(WithUnionAmbiguous, argv=[], env={}, files=[path])
        assert isinstance(result.shape, CircleShape)

    # --- Custom tag name ---

    def test_custom_tag_name_cli(self) -> None:
        """Custom union_tag='type' used in CLI."""
        result = confarg.load(
            WithUnionAmbiguous,
            argv=[
                "--shape.type",
                "tests.conftest.CircleShape",
                "--shape.x",
                "1",
                "--shape.y",
                "2",
                "--shape.radius",
                "5",
            ],
            env={},
            union_tag="type",
        )
        assert isinstance(result.shape, CircleShape)

    def test_custom_tag_name_env(self) -> None:
        """Custom union_tag='kind' used in env."""
        result = confarg.load(
            WithUnionAmbiguous,
            argv=[],
            env={
                "MYAPP_SHAPE__KIND": "tests.conftest.SquareShape",
                "MYAPP_SHAPE__X": "0",
                "MYAPP_SHAPE__Y": "0",
                "MYAPP_SHAPE__RADIUS": "3",
            },
            env_prefix="MYAPP_",
            union_tag="kind",
        )
        assert isinstance(result.shape, SquareShape)

    def test_custom_tag_name_toml(self, tmp_toml) -> None:
        """Custom union_tag='type' used in TOML."""
        path = tmp_toml("""\
            [shape]
            type = "tests.conftest.SquareShape"
            x = 0.0
            y = 0.0
            radius = 3.0
        """)
        result = confarg.load(WithUnionAmbiguous, argv=[], env={}, files=[path], union_tag="type")
        assert isinstance(result.shape, SquareShape)

    # --- Tag not needed when structural disambiguation works ---

    def test_tag_not_needed_when_fields_differ(self) -> None:
        """Rectangle has different fields; no tag needed even in a three-way Union."""
        result = confarg.load(
            WithUnionAmbiguousThree,
            argv=[
                "--shape.x",
                "0",
                "--shape.y",
                "0",
                "--shape.width",
                "10",
                "--shape.height",
                "20",
            ],
            env={},
        )
        assert isinstance(result.shape, RectangleShape)
        assert result.shape.width == pytest.approx(10.0)

    # --- Ambiguous without tag -> error ---

    def test_ambiguous_no_tag_raises(self) -> None:
        """Structurally identical Union without class tag raises AmbiguousUnionError."""
        with pytest.raises(confarg.exceptions.AmbiguousUnionError):
            confarg.load(
                WithUnionAmbiguous,
                argv=["--shape.x", "1", "--shape.y", "2", "--shape.radius", "5"],
                env={},
            )

    def test_ambiguous_no_tag_env_raises(self) -> None:
        """Structurally identical Union without class tag in env raises AmbiguousUnionError."""
        with pytest.raises(confarg.exceptions.AmbiguousUnionError):
            confarg.load(
                WithUnionAmbiguous,
                argv=[],
                env={"MYAPP_SHAPE__X": "1", "MYAPP_SHAPE__Y": "2", "MYAPP_SHAPE__RADIUS": "5"},
                env_prefix="MYAPP_",
            )

    def test_ambiguous_error_message_is_diagnostic(self) -> None:
        """AmbiguousUnionError lists candidates, their fields, and how to fix it."""
        with pytest.raises(confarg.exceptions.AmbiguousUnionError) as exc_info:
            confarg.load(
                WithUnionAmbiguous,
                argv=["--shape.x", "1", "--shape.y", "2", "--shape.radius", "5"],
                env={},
            )
        msg = str(exc_info.value)
        assert "CircleShape" in msg
        assert "SquareShape" in msg
        assert "required:" in msg
        assert "'class'" in msg
        assert "union_tag=" in msg

    # --- Invalid tag value -> error ---

    def test_invalid_tag_value_raises(self) -> None:
        """Class tag with a name not in the Union raises an error."""
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(
                WithUnionAmbiguous,
                argv=[
                    "--shape.class",
                    "TriangleShape",
                    "--shape.x",
                    "0",
                    "--shape.y",
                    "0",
                    "--shape.radius",
                    "1",
                ],
                env={},
            )

    # --- Tag overrides structural match ---

    @pytest.mark.parametrize(
        ("class_path", "expected_cls", "radius"),
        [
            ("tests.conftest.SquareShape", SquareShape, 7.0),
            ("tests.conftest.CircleShape", CircleShape, 9.0),
        ],
        ids=["square", "circle"],
    )
    def test_tag_overrides_in_three_way(self, class_path, expected_cls, radius) -> None:
        """In a three-way Union, tag selects the specified class."""
        result = confarg.load(
            WithUnionAmbiguousThree,
            argv=["--shape.class", class_path, "--shape.x", "0", "--shape.y", "0", "--shape.radius", str(radius)],
            env={},
        )
        assert isinstance(result.shape, expected_cls)
        assert result.shape.radius == radius

    # --- Fully-qualified class names ---

    @pytest.mark.parametrize(
        ("args_fn", "env_fn"),
        [
            (
                lambda fqn: ["--shape.class", fqn, "--shape.x", "1", "--shape.y", "2", "--shape.radius", "5"],
                lambda fqn: {},
            ),
            (
                lambda fqn: [],
                lambda fqn: {
                    "MYAPP_SHAPE__CLASS": fqn,
                    "MYAPP_SHAPE__X": "1",
                    "MYAPP_SHAPE__Y": "2",
                    "MYAPP_SHAPE__RADIUS": "5",
                },
            ),
        ],
        ids=["cli", "env"],
    )
    def test_tag_fully_qualified_name_cli_env(self, args_fn, env_fn) -> None:
        """Fully-qualified 'module.ClassName' is accepted as a class tag."""
        fqn = f"{CircleShape.__module__}.{CircleShape.__name__}"
        result = confarg.load(WithUnionAmbiguous, argv=args_fn(fqn), env=env_fn(fqn), env_prefix="MYAPP_")
        assert isinstance(result.shape, CircleShape)
        assert result.shape.radius == pytest.approx(5.0)

    def test_tag_fully_qualified_name_toml(self, tmp_toml) -> None:
        """Fully-qualified 'module.ClassName' is accepted as a class tag in TOML."""
        fqn = f"{CircleShape.__module__}.{CircleShape.__name__}"
        path = tmp_toml(f"""\
            [shape]
            class = "{fqn}"
            x = 1.0
            y = 2.0
            radius = 5.0
        """)
        result = confarg.load(WithUnionAmbiguous, argv=[], env={}, files=[path])
        assert isinstance(result.shape, CircleShape)
        assert result.shape.radius == pytest.approx(5.0)

    # --- Duplicate short names ---

    def test_tag_short_name_not_importable_raises(self) -> None:
        """A short (non-dotted) class name cannot be imported and raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.load(
                WithDuplicateNameUnion,
                argv=["--shape.class", "CircleShape", "--shape.x", "1", "--shape.y", "2", "--shape.radius", "5"],
                env={},
            )

    def test_tag_fqn_resolves_to_correct_class(self) -> None:
        """Fully-qualified tag imports and selects the right class."""
        fqn = f"{CircleShape.__module__}.{CircleShape.__name__}"
        result = confarg.load(
            WithDuplicateNameUnion,
            argv=["--shape.class", fqn, "--shape.x", "1", "--shape.y", "2", "--shape.radius", "5"],
            env={},
        )
        assert isinstance(result.shape, CircleShape)

    def test_serialize_duplicate_names_emits_fqn(self) -> None:
        """dump() emits fully-qualified class tag when two union variants share a short name."""
        instance = WithDuplicateNameUnion(shape=CircleShape(x=1.0, y=2.0, radius=5.0))
        data = confarg.dump(instance, tag_policy="always")
        tag = data["shape"]["class"]
        assert "." in tag, f"Expected fully-qualified name, got {tag!r}"
        assert tag == f"{CircleShape.__module__}.{CircleShape.__name__}"


# ---------------------------------------------------------------------------
# Nested lists of dataclasses
# ---------------------------------------------------------------------------


class TestNestedListOfDataclass:
    """Lists of nested dataclasses."""

    def test_nested_list_indexed_cli(self) -> None:
        """Parse list of dataclasses via indexed CLI args."""
        result = confarg.load(
            WithNestedList,
            argv=[
                "--servers.0.host",
                "a",
                "--servers.0.port",
                "1",
                "--servers.0.name",
                "db1",
                "--servers.1.host",
                "b",
                "--servers.1.port",
                "2",
                "--servers.1.name",
                "db2",
            ],
            env={},
        )
        assert len(result.servers) == 2
        assert result.servers[0].host == "a"
        assert result.servers[1].host == "b"


# ---------------------------------------------------------------------------
# Optional nested dataclass
# ---------------------------------------------------------------------------


class TestOptionalNested:
    """Optional nested dataclass."""

    def test_optional_nested_none(self) -> None:
        """Optional nested dataclass defaults to None."""
        result = confarg.load(WithOptionalNested, argv=[], env={})
        assert result.db is None

    def test_optional_nested_provided(self) -> None:
        """Optional nested dataclass parsed when subfields provided."""
        result = confarg.load(
            WithOptionalNested,
            argv=["--db.host", "h", "--db.port", "1", "--db.name", "n"],
            env={},
        )
        assert result.db is not None
        assert result.db.host == "h"

    def test_optional_nested_none_sentinel_unsets(self, tmp_toml) -> None:
        """--db none unsets Optional[DbConfig] to None."""
        path = tmp_toml("""\
            [db]
            host = "h"
            port = 1
            name = "n"
        """)
        result = confarg.load(WithOptionalNested, argv=["--db", "none"], env={}, files=[path])
        assert result.db is None


# ---------------------------------------------------------------------------
# Mixed collections
# ---------------------------------------------------------------------------


class TestMixedCollections:
    """Dataclass with multiple collection types."""

    def test_all_collections_from_cli(self) -> None:
        """Parse all collection types in one call."""
        result = confarg.load(
            WithCollections,
            argv=[
                "--names",
                "a",
                "b",
                "--counts",
                "1",
                "2",
                "3",
                "--tags",
                "x",
                "--mapping.key1",
                "10",
            ],
            env={},
        )
        assert result.names == ["a", "b"]
        assert result.tags == {"x"}
        assert result.mapping == {"key1": 10}


# ---------------------------------------------------------------------------
# CLI + Union disambiguation (Literal discriminators, type disagreement)
# ---------------------------------------------------------------------------


class TestCliUnionDisambiguation:
    """Tests for CLI parsing when Union variants disagree on field types."""

    def test_config_id2_cli_value_gives_str(self, tmp_toml) -> None:
        """Config id=2 selects TaggedStr; --entry.value true -> string "true"."""
        path = tmp_toml("""\
            [entry]
            id = 2
        """)
        result = confarg.load(
            WithTaggedUnion,
            argv=["--entry.value", "true"],
            env={},
            files=[path],
        )
        assert isinstance(result.entry, TaggedStr)
        assert result.entry.value == "true"
        assert result.entry.id == 2

    def test_config_id1_cli_value_gives_bool(self, tmp_toml) -> None:
        """Config id=1 selects TaggedBool; --entry.value true -> bool True."""
        path = tmp_toml("""\
            [entry]
            id = 1
        """)
        result = confarg.load(
            WithTaggedUnion,
            argv=["--entry.value", "true"],
            env={},
            files=[path],
        )
        assert isinstance(result.entry, TaggedBool)
        assert result.entry.value is True
        assert result.entry.id == 1

    def test_env_id2_value_gives_str(self) -> None:
        """Env ENTRY__ID=2 selects TaggedStr; ENTRY__VALUE=true -> string "true"."""
        result = confarg.load(
            WithTaggedUnion,
            argv=[],
            env={"MYAPP_ENTRY__ID": "2", "MYAPP_ENTRY__VALUE": "true"},
            env_prefix="MYAPP_",
        )
        assert isinstance(result.entry, TaggedStr)
        assert result.entry.value == "true"

    def test_env_id1_value_gives_bool(self) -> None:
        """Env ENTRY__ID=1 selects TaggedBool; ENTRY__VALUE=true -> bool True."""
        result = confarg.load(
            WithTaggedUnion,
            argv=[],
            env={"MYAPP_ENTRY__ID": "1", "MYAPP_ENTRY__VALUE": "true"},
            env_prefix="MYAPP_",
        )
        assert isinstance(result.entry, TaggedBool)
        assert result.entry.value is True

    def test_cli_literal_disambiguates_to_tagged_str(self) -> None:
        """CLI-only: --entry.id 2 --entry.value hello -> TaggedStr."""
        result = confarg.load(
            WithTaggedUnion,
            argv=["--entry.id", "2", "--entry.value", "hello"],
            env={},
        )
        assert isinstance(result.entry, TaggedStr)
        assert result.entry.value == "hello"

    def test_cli_literal_disambiguates_to_tagged_bool(self) -> None:
        """CLI-only: --entry.id 1 --entry.value false -> TaggedBool."""
        result = confarg.load(
            WithTaggedUnion,
            argv=["--entry.id", "1", "--entry.value", "false"],
            env={},
        )
        assert isinstance(result.entry, TaggedBool)
        assert result.entry.value is False

    def test_collection_vs_scalar_takes_one_value(self) -> None:
        """Variants disagree (list vs str) -> CLI consumes one value as string."""
        result = confarg.load(
            WithCollectionOrScalar,
            argv=["--entry.tag", "single", "--entry.data", "hello"],
            env={},
        )
        assert isinstance(result.entry, SingleVal)
        assert result.entry.data == "hello"

    def test_collection_vs_scalar_multi_variant(self, tmp_toml) -> None:
        """Config tag=multi selects MultiVal; indexed CLI provides list data."""
        path = tmp_toml("""\
            [entry]
            tag = "multi"
        """)
        result = confarg.load(
            WithCollectionOrScalar,
            argv=["--entry.data.0", "1", "--entry.data.1", "2", "--entry.data.2", "3"],
            env={},
            files=[path],
        )
        assert isinstance(result.entry, MultiVal)
        assert result.entry.data == [1, 2, 3]

    def test_agreed_bool_bare_flag(self) -> None:
        """Both variants have flag: bool -> --entry.flag true sets flag=True."""
        result = confarg.load(
            WithAgreedBoolUnion,
            argv=["--entry.id", "a", "--entry.flag", "true"],
            env={},
        )
        assert isinstance(result.entry, BoolVariantA)
        assert result.entry.flag is True

    def test_config_only_literal_discriminator(self, tmp_toml) -> None:
        """Pure config file with Literal discriminator selects correct variant."""
        path = tmp_toml("""\
            [entry]
            value = "hello"
            id = 2
        """)
        result = confarg.load(
            WithTaggedUnion,
            argv=[],
            env={},
            files=[path],
        )
        assert isinstance(result.entry, TaggedStr)
        assert result.entry.value == "hello"


# ---------------------------------------------------------------------------
# Union with type: Literal discriminator (canonical pattern)
# ---------------------------------------------------------------------------


class TestTypeLiteralDiscriminator:
    """Discriminated unions where 'type: Literal[...]' is the sole distinguishing field."""

    @pytest.mark.parametrize(
        ("args", "env", "expected_cls", "expected_value"),
        [
            (["--item.type", "a", "--item.value", "1"], {}, TypedVariantA, 1),
            (["--item.type", "b", "--item.value", "2"], {}, TypedVariantB, 2),
            ([], {"MYAPP_ITEM__TYPE": "a", "MYAPP_ITEM__VALUE": "10"}, TypedVariantA, 10),
            ([], {"MYAPP_ITEM__TYPE": "b", "MYAPP_ITEM__VALUE": "20"}, TypedVariantB, 20),
        ],
        ids=["cli-a", "cli-b", "env-a", "env-b"],
    )
    def test_type_literal_cli_env(self, args, env, expected_cls, expected_value) -> None:
        """Test Literal discriminator via CLI and env selects the correct union variant."""
        result = confarg.load(WithTypeLiteralUnion, argv=args, env=env, env_prefix="MYAPP_")
        assert isinstance(result.item, expected_cls)
        assert result.item.value == expected_value

    @pytest.mark.parametrize(
        ("type_val", "value", "expected_cls"),
        [("a", 42, TypedVariantA), ("b", 99, TypedVariantB)],
        ids=["a", "b"],
    )
    def test_type_literal_toml(self, tmp_toml, type_val, value, expected_cls) -> None:
        """Test Literal discriminator in TOML selects the correct union variant."""
        path = tmp_toml(f'[item]\ntype = "{type_val}"\nvalue = {value}\n')
        result = confarg.load(WithTypeLiteralUnion, argv=[], env={}, files=[path])
        assert isinstance(result.item, expected_cls)
        assert result.item.value == value

    def test_invalid_type_value_raises(self) -> None:
        """Type field value not in any Literal raises an error."""
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(
                WithTypeLiteralUnion,
                argv=["--item.type", "c", "--item.value", "1"],
                env={},
            )

    def test_no_type_field_raises(self) -> None:
        """Omitting the type discriminator means neither variant can be constructed."""
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(
                WithTypeLiteralUnion,
                argv=["--item.value", "1"],
                env={},
            )

    def test_cli_overrides_toml_type(self, tmp_toml) -> None:
        """CLI --item.type b overrides TOML type = "a"."""
        path = tmp_toml("""\
            [item]
            type = "a"
            value = 5
        """)
        result = confarg.load(
            WithTypeLiteralUnion,
            argv=["--item.type", "b"],
            env={},
            files=[path],
        )
        assert isinstance(result.item, TypedVariantB)


# ---------------------------------------------------------------------------
# Union float/str ambiguity (inf / nan)
# ---------------------------------------------------------------------------


class TestUnionFloatStrAmbiguity:
    """Edge cases where 'inf'/'nan' strings match both float and str."""

    def test_cli_inf_ambiguous_float_vs_str(self) -> None:
        """CLI --item.value inf is ambiguous: 'inf' parses as both float and str."""
        with pytest.raises(confarg.exceptions.AmbiguousUnionError):
            confarg.load(
                WithUnionFloatStr,
                argv=["--item.value", "inf"],
                env={},
            )

    def test_cli_nan_ambiguous_float_vs_str(self) -> None:
        """CLI --item.value nan is ambiguous: 'nan' parses as both float and str."""
        with pytest.raises(confarg.exceptions.AmbiguousUnionError):
            confarg.load(
                WithUnionFloatStr,
                argv=["--item.value", "nan"],
                env={},
            )

    def test_toml_native_float_inf_not_ambiguous(self, tmp_toml) -> None:
        """TOML value = inf is a native float -> resolves to FloatHolder."""
        path = tmp_toml("""\
            [item]
            value = inf
        """)
        result = confarg.load(WithUnionFloatStr, argv=[], env={}, files=[path])
        assert isinstance(result.item, FloatHolder)
        assert result.item.value == float("inf")

    def test_toml_str_inf_not_ambiguous(self, tmp_toml) -> None:
        """TOML value = "inf" is a plain str — cannot coerce to float, resolves to StrHolder."""
        path = tmp_toml("""\
            [item]
            value = "inf"
        """)
        result = confarg.load(WithUnionFloatStr, argv=[], env={}, files=[path])
        assert isinstance(result.item, StrHolder)
        assert result.item.value == "inf"

    def test_class_tag_resolves_inf_ambiguity(self) -> None:
        """CLI --item.class tests.conftest.FloatHolder --item.value inf resolves to FloatHolder."""
        result = confarg.load(
            WithUnionFloatStr,
            argv=["--item.class", "tests.conftest.FloatHolder", "--item.value", "inf"],
            env={},
        )
        assert isinstance(result.item, FloatHolder)
        assert result.item.value == float("inf")


# ---------------------------------------------------------------------------
# A builtin's subclass is that builtin
# ---------------------------------------------------------------------------


class _Scores(dict[str, int]):
    pass


class _Registry[T](dict[str, T]):
    pass


class _Votes(collections.Counter[str]):
    pass


class _OrderedScores(collections.OrderedDict[str, int]):
    pass


class _OwnDict(dict):
    def __init__(self, mapping: dict | None = None, *, strict: bool = False) -> None:
        super().__init__(mapping or {})
        self.strict = strict


class _KeywordOnlyDict(dict):
    def __init__(self, *, tag: str) -> None:
        super().__init__()
        self.tag = tag


class _Words(str):
    __slots__ = ()


class _Pair(tuple):
    __slots__ = ()


class _Bag(frozenset):
    __slots__ = ()


class _TypedMap(TypedDict):
    a: int


class _Mode(enum.StrEnum):
    FAST = "fast"


@dataclass
class _Sub:
    n: int = 0


@dataclass
class _DataclassDict(dict):
    a: int = 0


class TestABuiltinSubclassIsThatBuiltin:
    """A subclass of dict, list, set, frozenset, tuple, str, int or float reads as it and is built as itself."""

    @pytest.mark.parametrize(
        ("tp", "data", "expected"),
        [
            pytest.param(collections.OrderedDict[str, int], {"a": 1}, collections.OrderedDict(a=1), id="ordereddict"),
            pytest.param(collections.OrderedDict, {"a": "x"}, collections.OrderedDict(a="x"), id="bare-ordereddict"),
            pytest.param(collections.Counter[str], {"a": -2}, collections.Counter(a=-2), id="counter"),
            pytest.param(_Scores, {"a": 1}, _Scores(a=1), id="parameterized-base"),
            pytest.param(_Registry[int], {"a": 1}, _Registry(a=1), id="typevar-bound"),
            pytest.param(_Registry, {"a": "x"}, _Registry(a="x"), id="typevar-unbound"),
            pytest.param(_Votes, {"a": 2}, _Votes(a=2), id="counter-subclass"),
            pytest.param(_OrderedScores, {"a": 1}, _OrderedScores(a=1), id="ordereddict-subclass"),
            pytest.param(_OwnDict, {"strict": True}, _OwnDict({"strict": True}), id="own-constructor"),
            pytest.param(_Words, "ab", _Words("ab"), id="str"),
            pytest.param(_Pair, [1, "a"], _Pair((1, "a")), id="bare-tuple"),
            pytest.param(_Bag, [1, 1], _Bag({1}), id="frozenset"),
        ],
    )
    def test_a_file_value_builds_the_subclass(self, tp: Any, data: Any, expected: Any) -> None:
        """The value is read as the builtin, typed by the subclass's parameters, then given to the class."""
        Target = make_target("x", tp, default=None)
        built = confarg.build(Target, {"x": data}).x
        assert built == expected
        assert type(built) is type(expected)

    @pytest.mark.parametrize(
        ("tp", "data", "message"),
        [
            pytest.param(_Scores, {"a": "x"}, "Cannot coerce str 'x' to int at 'x.a'", id="base-parameter"),
            pytest.param(_Registry[int], {"a": "x"}, "Cannot coerce str 'x' to int at 'x.a'", id="typevar"),
            pytest.param(collections.Counter[str], {"a": 2.5}, "Cannot coerce float 2.5 to int at 'x.a'", id="count"),
        ],
    )
    def test_the_items_are_typed_by_the_subclass(self, tp: Any, data: Any, message: str) -> None:
        """The item types come from the subclass's arguments, its parameterized bases, or a Counter's counts."""
        Target = make_target("x", tp, default=None)
        with pytest.raises(TypeCoercionError, match=re.escape(message)):
            confarg.build(Target, {"x": data})

    def test_a_constructor_refusing_the_value_is_named(self) -> None:
        """A class whose constructor takes no dict is refused naming it, and the registration that reads it."""
        Target = make_target("x", _KeywordOnlyDict, default=None)
        with pytest.raises(TypeCoercionError, match=re.escape("_KeywordOnlyDict at 'x' does not take a dict")):
            confarg.build(Target, {"x": {"a": 1}})

    @pytest.mark.parametrize(
        ("value_type", "factory"),
        [
            pytest.param(list[int], list, id="list"),
            pytest.param(int, int, id="int"),
            pytest.param(_Sub, _Sub, id="struct"),
            pytest.param(dict[str, int], dict, id="dict"),
            pytest.param(Any, None, id="any"),
            pytest.param(int | str, None, id="union"),
        ],
    )
    def test_a_defaultdict_factory_is_the_value_types_class(self, value_type: Any, factory: Any) -> None:
        """The factory is the class construction builds a value as, None where no one class is it."""
        Target = make_target("x", collections.defaultdict[str, value_type], default=None)
        built = confarg.build(Target, {"x": {}}).x
        assert type(built) is collections.defaultdict
        assert built.default_factory is factory

    def test_a_dataclass_keeps_its_fields(self) -> None:
        """A dataclass subclassing dict is a struct, its declared fields winning over the base."""
        Target = make_target("x", _DataclassDict, default_factory=_DataclassDict)
        built = confarg.build(Target, {"x": {"a": 3}}).x
        assert built.a == 3
        assert dict(built) == {}

    @pytest.mark.parametrize("suffix", [".json", ".toml", ".yaml"])
    @pytest.mark.parametrize(
        ("tp", "value", "written"),
        [
            pytest.param(str, _Words("hi"), "hi", id="str-field"),
            pytest.param(Any, collections.OrderedDict(a=1), {"a": 1}, id="any-mapping"),
        ],
    )
    def test_a_subclass_value_is_written_as_its_builtin(
        self,
        tmp_path: Any,
        suffix: str,
        tp: Any,
        value: Any,
        written: Any,
    ) -> None:
        """Whatever the field's type, a subclass instance leaves as the builtin, which every writer holds."""
        Target = make_target("x", tp, default=None)
        dumped = confarg.dump(Target(x=value))
        assert dumped == {"x": written}
        assert type(dumped["x"]) is type(written)
        confarg.dump_file(Target(x=value), tmp_path / f"c{suffix}")
        assert confarg.load(Target, argv=[], env={}, files=[tmp_path / f"c{suffix}"]).x == written

    @pytest.mark.parametrize("suffix", [".json", ".toml", ".yaml"])
    def test_an_any_field_writes_a_subclass_as_its_builtin(self, tmp_path: Any, suffix: str) -> None:
        """An ``Any`` field reads the builtin back, not the subclass, and its dump says so."""
        Target = make_target("x", Any, default=None)
        with pytest.warns(ConfargWarning, match=re.escape("will not read back as the _Words it holds")):
            confarg.dump_file(Target(x=_Words("hi")), tmp_path / f"c{suffix}")
        assert confarg.load(Target, argv=[], env={}, files=[tmp_path / f"c{suffix}"]).x == "hi"

    def test_a_typeddict_is_left_to_its_own_reading(self) -> None:
        """A ``TypedDict`` subclasses dict at runtime, yet types each key: it is no untyped dict (FEAT-45)."""
        Target = make_target("x", _TypedMap, default=None)
        with pytest.raises(TypeCoercionError, match=re.escape("Unknown field(s) ['a'] for _TypedMap at 'x'")):
            confarg.build(Target, {"x": {"a": 3}})

    def test_a_str_enum_stays_an_enum(self) -> None:
        """A ``StrEnum`` subclasses str, and reads as its members still."""
        Target = make_target("x", _Mode, default=_Mode.FAST)
        assert confarg.build(Target, {"x": "FAST"}).x is _Mode.FAST

    @pytest.mark.parametrize(
        ("tp", "value", "written"),
        [
            pytest.param(collections.OrderedDict[str, int], collections.OrderedDict(a=1), {"a": 1}, id="ordereddict"),
            pytest.param(collections.Counter[str], collections.Counter(a=2), {"a": 2}, id="counter"),
            pytest.param(_Words, _Words("ab"), "ab", id="str"),
            pytest.param(_Pair, _Pair((1, 2)), [1, 2], id="tuple"),
        ],
    )
    def test_a_dump_writes_the_builtin(self, tp: Any, value: Any, written: Any) -> None:
        """The dump holds the plain builtin a writer knows, and reads back as the subclass."""
        Target = make_target("x", tp, default=None)
        dumped = confarg.dump(Target(x=value))
        assert dumped == {"x": written}
        assert type(dumped["x"]) is type(written)
        assert type(confarg.build(Target, dumped).x) is type(value)

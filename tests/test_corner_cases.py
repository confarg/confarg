# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Corner-case tests covering edge cases identified during code review.

Covers: non-integer dict keys for collections, deep merge errors, camelCase env
matching, negated flags with prefix, repeated collections, bool edge cases,
sparse lists, fixed-tuple length mismatches, union edge cases, expression edge
cases, serialization edge cases, and more.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union

import pytest

import confarg
from confarg._errors import ConfargError, TypeCoercionError
from confarg._merge import _deep_merge
from confarg._types import _is_frozenset, _is_set, _StrToken
from confarg.dictexpr import resolve_expressions
from confarg.typedload import construct
from confarg.typedload._coerce import _coerce_leaf
from tests.conftest import (
    AppConfig,
    CacheConfig,
    CircleShape,
    Color,
    DbConfig,
    Empty,
    Flat,
    PgConfig,
    ServerTcp,
    SquareShape,
    WithDefaults,
    WithNestedList,
    WithOptionalNested,
    WithUnionAmbiguous,
    WithUnionDisjointDefaults,
    WithUnionNested,
    WithUnionOverlap,
    make_target,
)

# ---------------------------------------------------------------------------
# Module-level dataclasses for env matching tests (needed because
# `from __future__ import annotations` makes annotations strings,
# which can't resolve classes defined in local function scope).
# ---------------------------------------------------------------------------


@dataclass
class CamelCaseConfig:
    """Dataclass with camelCase field names."""

    dbHost: str = "localhost"
    dbPort: int = 5432


@dataclass
class MixedCaseConfig:
    """Dataclass with mixed-case field names."""

    MyField: str = "default"


@dataclass
class InnerCamel:
    """Inner dataclass with camelCase field names."""

    serverName: str = "default"


@dataclass
class OuterCamel:
    """Outer dataclass containing an InnerCamel."""

    inner: InnerCamel


@dataclass
class AmbiguousFields:
    """Dataclass with two fields that differ only in case."""

    name: str = "a"
    Name: str = "b"


@dataclass
class _ServerVariant:
    host: str
    port: int
    name: str


@dataclass
class _SqliteVariant:
    dbpath: str


# ===========================================================================
# Non-integer dict keys for list/set/tuple (Fix #2)
# ===========================================================================


class TestNonIntegerDictKeysForCollections:
    """Dict data with non-integer keys should raise TypeCoercionError, not ValueError."""

    def test_list_with_non_integer_keys_from_toml(self, tmp_toml) -> None:
        """TOML table used where an array was expected raises TypeCoercionError."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("""\
            [items]
            name = "oops"
        """)
        with pytest.raises(TypeCoercionError, match="integer indices"):
            confarg.load(WithList, args=[], env={}, files=[path])

    def test_set_with_non_integer_keys(self) -> None:
        """Set from dict with non-integer keys raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="integer indices"):
            construct(set[str], {"name": "oops"}, path="tags")

    def test_tuple_with_non_integer_keys(self) -> None:
        """Tuple from dict with non-integer keys raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="integer indices"):
            construct(tuple[int, str], {"name": "oops"}, path="pair")

    def test_list_with_mixed_keys(self) -> None:
        """List from dict with mix of integer and non-integer keys raises."""
        with pytest.raises(TypeCoercionError, match="integer indices"):
            construct(list[int], {"0": 1, "name": "oops"}, path="items")


# ===========================================================================
# _deep_merge list patching with non-integer keys (Fix #3)
# ===========================================================================


class TestDeepMergeListPatchErrors:
    """_deep_merge should raise when patching a list with non-integer dict keys."""

    def test_non_integer_key_raises(self) -> None:
        """Patching a list with a non-integer key raises ConfargError."""
        base = {"items": [1, 2, 3]}
        override = {"items": {"name": "bad"}}
        with pytest.raises(ConfargError, match="non-integer key"):
            _deep_merge(base, override)

    def test_integer_key_still_works(self) -> None:
        """Patching a list with integer keys still works correctly."""
        base = {"items": [1, 2, 3]}
        override = {"items": {"1": 99}}
        result = _deep_merge(base, override)
        assert result["items"] == [1, 99, 3]

    def test_out_of_range_index_raises(self) -> None:
        """Patching a list with an index beyond its length raises ConfargError."""
        base = {"items": [1, 2]}
        override = {"items": {"4": 99}}
        with pytest.raises(ConfargError, match="append syntax"):
            _deep_merge(base, override)

    def test_negative_index_patches_from_end(self) -> None:
        """Negative indices count from the end of the list, like Python."""
        base = {"items": [1, 2, 3]}
        result = _deep_merge(base, {"items": {"-1": 99}})
        assert result["items"] == [1, 2, 99]
        result = _deep_merge(base, {"items": {"-3": 99}})
        assert result["items"] == [99, 2, 3]

    def test_negative_index_oob_raises(self) -> None:
        """Index -4 on a 3-element list is out of range and raises ConfargError."""
        base = {"items": [1, 2, 3]}
        with pytest.raises(ConfargError, match="-4"):
            _deep_merge(base, {"items": {"-4": 99}})

    def test_negative_delete_index(self) -> None:
        """{"-": [-1]} deletes the last element."""
        from confarg._merge import LIST_DELETE_KEY

        base = {"items": [1, 2, 3]}
        result = _deep_merge(base, {"items": {LIST_DELETE_KEY: [-1]}})
        assert result["items"] == [1, 2]

    def test_negative_delete_oob_raises(self) -> None:
        """Deleting index -4 from a 3-element list raises ConfargError."""
        from confarg._merge import LIST_DELETE_KEY

        base = {"items": [1, 2, 3]}
        with pytest.raises(ConfargError, match="-4"):
            _deep_merge(base, {"items": {LIST_DELETE_KEY: [-4]}})

    def test_negative_minus_zero_key_raises(self) -> None:
        """Index -0 is numerically 0 but the string '-0' parses as 0, not negative."""
        base = {"items": [1, 2, 3]}
        override = {"items": {"-0": 99}}
        # int("-0") == 0, so this is valid and replaces index 0
        result = _deep_merge(base, override)
        assert result["items"] == [99, 2, 3]


# ===========================================================================
# Case-insensitive env var matching (Fix #4)
# ===========================================================================


class TestCaseInsensitiveEnvMatching:
    """Env var parts should match field names case-insensitively."""

    def test_camel_case_field(self) -> None:
        """CamelCase field matched by uppercase env var."""
        result = confarg.load(CamelCaseConfig, args=[], env={"DBHOST": "prod", "DBPORT": "3306"}, env_prefix="")
        assert result.dbHost == "prod"
        assert result.dbPort == 3306

    def test_mixed_case_field(self) -> None:
        """MixedCase field matched by lowercase env var parts."""
        result = confarg.load(MixedCaseConfig, args=[], env={"MYFIELD": "overridden"}, env_prefix="")
        assert result.MyField == "overridden"

    def test_nested_camel_case_field(self) -> None:
        """Nested camelCase field matched from env."""
        result = confarg.load(OuterCamel, args=[], env={"INNER__SERVERNAME": "prod-server"}, env_prefix="")
        assert result.inner.serverName == "prod-server"

    def test_snake_case_still_works(self) -> None:
        """Regular snake_case fields still work as before."""
        result = confarg.load(WithDefaults, args=[], env={"NAME": "test", "COUNT": "42"}, env_prefix="")
        assert result.name == "test"
        assert result.count == 42

    def test_case_insensitive_with_prefix(self) -> None:
        """CamelCase matching works with env prefix."""
        result = confarg.load(CamelCaseConfig, args=[], env={"APP__DBHOST": "custom"}, env_prefix="APP")
        assert result.dbHost == "custom"

    def test_ambiguous_fields_raises(self) -> None:
        """Fields that differ only in case raise ConfargError."""
        with pytest.raises(ConfargError, match=r"[Aa]mbiguous"):
            confarg.load(AmbiguousFields, args=[], env={"NAME": "val"}, env_prefix="")


# ===========================================================================
# CLI edge cases
# ===========================================================================


class TestCliCornerCases:
    """Edge cases for CLI argument parsing."""

    def test_negated_flag_with_prefix_for_nested(self) -> None:
        """--app.debug false with cli_prefix='app' correctly sets debug=False."""
        result = confarg.load(
            AppConfig,
            args=[
                "--app.db.host",
                "h",
                "--app.db.port",
                "1",
                "--app.db.name",
                "n",
                "--app.debug",
                "false",
            ],
            env={},
            cli_prefix="app",
        )
        assert result.debug is False

    def test_repeated_varlen_collection_last_wins(self) -> None:
        """Repeated --items overwrites previous values (last wins)."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(
            WithList,
            args=["--items", "1", "2", "--items", "3", "4"],
            env={},
        )
        # Second --items replaces the first
        assert result.items == [3, 4]

    def test_varlen_collection_stops_at_flag(self) -> None:
        """Variable-length collection stops consuming at the next --flag."""
        WithList = make_target("items", list[str], default_factory=list)
        result = confarg.load(
            WithList,
            args=["--items", "a", "b", "--items", "c", "d"],
            env={},
        )
        # Second --items overwrites the first (last wins)
        assert result.items == ["c", "d"]

    def test_negative_number_as_value(self) -> None:
        """Negative numbers like -5 are not treated as flags."""
        result = confarg.load(
            WithDefaults,
            args=["--count", "-999"],
            env={},
        )
        assert result.count == -999

    def test_double_dash_number_is_not_a_flag(self) -> None:
        """--3.14 is not treated as a flag, so it's consumed as a value.

        However, the raw string '--3.14' is not a valid float, so coercion
        fails. For negative numbers, use single dash: -3.14.
        """
        with pytest.raises(confarg.TypeCoercionError):
            confarg.load(
                WithDefaults,
                args=["--rate", "--3.14"],
                env={},
            )

    def test_empty_string_as_cli_value(self) -> None:
        """Empty string as CLI value is preserved."""
        result = confarg.load(
            WithDefaults,
            args=["--name", ""],
            env={},
        )
        assert result.name == ""

    def test_positional_arg_raises(self) -> None:
        """Positional arguments without -- raise UnknownArgumentError."""
        with pytest.raises(confarg.UnknownArgumentError, match="positional"):
            confarg.load(WithDefaults, args=["hello"], env={})

    def test_config_flag_missing_path(self) -> None:
        """--config without a following path raises ConfargError."""
        with pytest.raises(confarg.ConfargError, match="Missing file path"):
            confarg.load(WithDefaults, args=["--config"], env={})


# ===========================================================================
# Bool edge cases
# ===========================================================================


class TestBoolEdgeCases:
    """Edge cases for boolean coercion."""

    def test_int_2_for_bool_raises(self) -> None:
        """Integer 2 for a bool field raises TypeCoercionError (not in truthy/falsy)."""
        with pytest.raises(confarg.TypeCoercionError):
            confarg.load(WithDefaults, args=[], env={"VERBOSE": "2"}, env_prefix="")

    def test_int_0_for_bool_false(self) -> None:
        """Integer 0 for a bool field gives False."""
        result = confarg.load(WithDefaults, args=[], env={"VERBOSE": "0"}, env_prefix="")
        assert result.verbose is False

    def test_int_1_for_bool_true(self) -> None:
        """Integer 1 for a bool field gives True."""
        result = confarg.load(WithDefaults, args=[], env={"VERBOSE": "1"}, env_prefix="")
        assert result.verbose is True

    def test_random_string_for_bool_raises(self) -> None:
        """Random string for bool field raises TypeCoercionError."""
        with pytest.raises(confarg.TypeCoercionError):
            confarg.load(WithDefaults, args=[], env={"VERBOSE": "yesno"}, env_prefix="")

    def test_invalid_bool_error_lists_valid_values(self) -> None:
        """TypeCoercionError for an invalid bool string lists the accepted tokens."""
        with pytest.raises(confarg.TypeCoercionError, match=r"Valid values:.*false.*true"):
            confarg.load(WithDefaults, args=[], env={"VERBOSE": "enabled"}, env_prefix="")

    def test_native_bool_from_toml(self, tmp_toml) -> None:
        """Native TOML boolean is passed through directly."""
        path = tmp_toml("verbose = true\n")
        result = confarg.load(WithDefaults, args=[], env={}, files=[path])
        assert result.verbose is True

    def test_bool_coercion_from_int_in_toml_raises(self, tmp_toml) -> None:
        """TOML integer 1 for a bool field raises TypeCoercionError (use true/false in TOML)."""
        path = tmp_toml("verbose = 1\n")
        with pytest.raises(confarg.TypeCoercionError):
            confarg.load(WithDefaults, args=[], env={}, files=[path])


# ===========================================================================
# Sparse lists
# ===========================================================================


class TestSparseLists:
    """Sparse list construction from indexed data."""

    def test_sparse_list_from_cli_optional_elem(self) -> None:
        """Gaps in list[str | None] are filled with None via construct."""
        WithList = make_target("items", list[str | None], default_factory=list)
        result = confarg.load(WithList, args=["--items.3", "hello"], env={})
        assert len(result.items) == 4
        assert result.items[3] == "hello"
        assert result.items[0] is None
        assert result.items[1] is None
        assert result.items[2] is None

    def test_sparse_list_non_optional_elem_raises(self) -> None:
        """Gaps in list[int] (non-optional element) raise TypeCoercionError naming the gap indices."""
        WithList = make_target("items", list[int], default_factory=list)
        with pytest.raises(confarg.TypeCoercionError, match=r"gap.*\[0, 1\]"):
            confarg.load(WithList, args=["--items.2", "42"], env={})

    def test_sparse_list_from_env_optional_elem(self) -> None:
        """Sparse indices via env vars fill gaps with None for Optional element types."""
        WithList = make_target("items", list[int | None], default_factory=list)
        result = confarg.load(WithList, args=[], env={"ITEMS__2": "42"}, env_prefix="")
        assert len(result.items) == 3
        assert result.items[2] == 42
        assert result.items[0] is None
        assert result.items[1] is None

    def test_sparse_list_from_env_non_optional_raises(self) -> None:
        """Gaps in list[int] from env var raise TypeCoercionError naming the gap indices."""
        WithList = make_target("items", list[int], default_factory=list)
        with pytest.raises(confarg.TypeCoercionError, match=r"gap.*\[0, 1\]"):
            confarg.load(WithList, args=[], env={"ITEMS__2": "42"}, env_prefix="")

    def test_index_beyond_config_list_raises(self, tmp_toml) -> None:
        """Env index beyond the config list length raises ConfargError (replacement-only policy)."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        with pytest.raises(ConfargError, match="append syntax"):
            confarg.load(WithList, args=[], env={"ITEMS__4": "99"}, env_prefix="", files=[path])

    def test_index_beyond_optional_list_also_raises(self, tmp_toml) -> None:
        """Index beyond list length raises even for list[int | None] — use + syntax instead."""
        WithList = make_target("items", list[int | None], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        with pytest.raises(ConfargError, match="append syntax"):
            confarg.load(WithList, args=[], env={"ITEMS__4": "99"}, env_prefix="", files=[path])


# ===========================================================================
# Fixed-length tuple edge cases
# ===========================================================================


class TestFixedTupleEdgeCases:
    """Edge cases for fixed-length tuple construction."""

    def test_fewer_values_than_expected_raises(self) -> None:
        """Fewer values than fixed tuple length raises for non-optional element types."""
        WithTuple = make_target("pair", tuple[str, int], default=("", 0))
        # Only one value provided for a 2-element tuple: missing int can't be None
        with pytest.raises(TypeCoercionError):
            confarg.load(WithTuple, args=["--pair", "hello"], env={})

    def test_fewer_values_optional_element(self) -> None:
        """Fewer values with optional element type fills with None."""
        WithTuple = make_target("pair", tuple[str, int | None], default=("", None))
        result = confarg.load(WithTuple, args=["--pair", "hello"], env={})
        assert result.pair[0] == "hello"
        assert result.pair[1] is None

    def test_exact_values(self) -> None:
        """Exact number of values for fixed-length tuple."""
        WithTuple = make_target("triple", tuple[str, int, float], default=("", 0, 0.0))
        result = confarg.load(WithTuple, args=["--triple", "a", "42", "1.5"], env={})
        assert result.triple == ("a", 42, pytest.approx(1.5))

    def test_empty_tuple(self) -> None:
        """Empty tuple type with no values."""
        WithTuple = make_target("empty", tuple[()], default=())
        result = confarg.load(WithTuple, args=[], env={})
        assert result.empty == ()

    def test_variable_length_tuple_from_cli(self) -> None:
        """Variable-length tuple from CLI space-separated values."""
        WithVarTuple = make_target("items", tuple[int, ...], default=())
        result = confarg.load(WithVarTuple, args=["--items", "1", "2", "3"], env={})
        assert result.items == (1, 2, 3)


# ===========================================================================
# Dict construction edge cases
# ===========================================================================


class TestDictEdgeCases:
    """Edge cases for dict construction."""

    def test_dict_with_int_keys(self) -> None:
        """Dict with int key type from CLI."""
        WithDict = make_target("mapping", dict[int, str], default_factory=dict)
        result = confarg.load(WithDict, args=["--mapping.1", "a", "--mapping.2", "b"], env={})
        assert result.mapping == {1: "a", 2: "b"}

    def test_dict_empty_value(self) -> None:
        """Dict with empty string value from CLI."""
        WithDict = make_target("mapping", dict[str, str], default_factory=dict)
        result = confarg.load(WithDict, args=["--mapping.key", ""], env={})
        assert result.mapping == {"key": ""}

    def test_dict_from_non_dict_data(self) -> None:
        """Dict field with non-dict data raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="expected dict"):
            construct(dict[str, int], "not_a_dict", path="field")

    def test_dict_nested_dataclass_values(self, tmp_toml) -> None:
        """Dict with dataclass values from config file."""
        WithDcDict = make_target("servers", dict[str, DbConfig], default_factory=dict)
        path = tmp_toml("""\
            [servers.primary]
            host = "h1"
            port = 5432
            name = "db1"

            [servers.secondary]
            host = "h2"
            port = 5433
            name = "db2"
        """)
        result = confarg.load(WithDcDict, args=[], env={}, files=[path])
        assert result.servers["primary"].host == "h1"
        assert result.servers["secondary"].port == 5433


# ===========================================================================
# Union edge cases
# ===========================================================================


@dataclass
class _NoFieldBase:
    pass


@dataclass
class _UnrelatedDc:
    value: float


@dataclass
class _OuterWithNoFieldBase:
    inner: _NoFieldBase


class TestUnionCornerCases:
    """Additional union disambiguation edge cases."""

    def test_union_bool_str_with_truthy_value(self) -> None:
        """Union[bool, str]: 'true' should be coerced to bool (tried first)."""
        WithUnion = make_target("value", Union[bool, str], default=False)
        result = confarg.load(WithUnion, args=[], env={"VALUE": "true"}, env_prefix="")
        assert result.value is True
        assert isinstance(result.value, bool)

    def test_union_bool_str_with_non_truthy(self) -> None:
        """Union[bool, str]: 'hello' is not truthy, falls through to str."""
        WithUnion = make_target("value", Union[bool, str], default=False)
        result = confarg.load(WithUnion, args=[], env={"VALUE": "hello"}, env_prefix="")
        assert result.value == "hello"
        assert isinstance(result.value, str)

    def test_union_int_str_none_empty_string(self) -> None:
        """Union[int, str, None]: empty string stays as empty string (str is in union)."""
        WithUnion = make_target("value", Union[int, str, None], default=None)
        result = confarg.load(WithUnion, args=[], env={"VALUE": ""}, env_prefix="")
        assert result.value == ""

    def test_union_int_none_empty_string(self) -> None:
        """Union[int, None]: empty string raises TypeCoercionError (use --value.None instead)."""
        WithUnion = make_target("value", Union[int, None], default=None)
        with pytest.raises(TypeCoercionError, match="To set this field to None"):
            confarg.load(WithUnion, args=[], env={"VALUE": ""}, env_prefix="")

    def test_union_none_only_variant(self) -> None:
        """Optional[int] with --value none: sets to None."""
        WithOptional = make_target("value", Optional[int], default=42)
        result = confarg.load(WithOptional, args=["--value", "none"], env={})
        assert result.value is None

    def test_union_dataclass_vs_leaf_with_dict(self, tmp_toml) -> None:
        """Union[int, DbConfig]: dict data → DbConfig (int can't accept dict)."""
        path = tmp_toml("""\
            [value]
            host = "h"
            port = 1
            name = "n"
        """)
        result = confarg.load(WithUnionNested, args=[], env={}, files=[path])
        assert isinstance(result.value, DbConfig)
        assert result.value.host == "h"

    def test_union_single_variant_no_fallback_to_none(self) -> None:
        """Union[int, None] with non-numeric string raises (no silent fallback to None)."""
        WithUnion = make_target("value", Union[int, None], default=None)
        with pytest.raises(TypeCoercionError):
            confarg.load(WithUnion, args=[], env={"VALUE": "not_a_number"}, env_prefix="")

    def test_union_class_tag_invalid_name(self) -> None:
        """Non-importable class tag raises TypeCoercionError."""
        with pytest.raises(confarg.TypeCoercionError, match="Cannot import class"):
            confarg.load(
                WithUnionAmbiguous,
                args=[
                    "--shape.class",
                    "NonExistent",
                    "--shape.x",
                    "0",
                    "--shape.y",
                    "0",
                    "--shape.radius",
                    "1",
                ],
                env={},
            )

    def test_class_tag_on_non_subclass_raises(self, tmp_yaml) -> None:
        """Class tag naming a type that is not a subclass of the field type raises TypeCoercionError."""
        path = tmp_yaml("inner:\n  class: tests.test_corner_cases._UnrelatedDc\n")
        with pytest.raises(TypeCoercionError, match="not a subclass"):
            confarg.load(_OuterWithNoFieldBase, args=[], env={}, files=[path])

    def test_union_native_typed_data_from_toml(self, tmp_toml) -> None:
        """TOML native int resolves Union[ServerTcp, ServerUnix] to ServerTcp."""
        path = tmp_toml("""\
            [server]
            host = "h"
            port = 5432
        """)
        result = confarg.load(WithUnionOverlap, args=[], env={}, files=[path])
        assert isinstance(result.server, ServerTcp)
        assert result.server.port == 5432


# ===========================================================================
# Nested dataclass auto-instantiation
# ===========================================================================


class TestNestedDataclassAutoInstantiation:
    """Nested dataclass with all defaults is auto-instantiated."""

    def test_nested_all_defaults_auto_created(self) -> None:
        """Nested dataclass with all defaults is auto-created even without data."""
        result = confarg.load(
            AppConfig,
            args=["--db.host", "h", "--db.port", "1", "--db.name", "n"],
            env={},
        )
        # CacheConfig has all defaults, should be auto-instantiated
        assert isinstance(result.cache, CacheConfig)
        assert result.cache.enabled is True
        assert result.cache.ttl == 300

    def test_optional_nested_not_auto_created(self) -> None:
        """Optional[DbConfig] is NOT auto-created — stays None."""
        result = confarg.load(WithOptionalNested, args=[], env={})
        assert result.db is None


# ===========================================================================
# Config file edge cases
# ===========================================================================


class TestConfigFileCornerCases:
    """Edge cases for config file loading."""

    def test_toml_empty_file(self, tmp_path: Path) -> None:
        """Empty TOML file produces no values, defaults used."""
        p = tmp_path / "empty.toml"
        p.write_text("")
        result = confarg.load(WithDefaults, args=[], env={}, files=[p])
        assert result.name == "default"

    def test_yaml_empty_file(self, tmp_path: Path) -> None:
        """Empty YAML file produces no values, defaults used."""
        p = tmp_path / "empty.yaml"
        p.write_text("")
        result = confarg.load(WithDefaults, args=[], env={}, files=[p])
        assert result.name == "default"

    def test_yaml_non_dict_content(self, tmp_path: Path) -> None:
        """YAML file with non-dict content (e.g. a list) is treated as empty."""
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n")
        result = confarg.load(WithDefaults, args=[], env={}, files=[p])
        assert result.name == "default"

    def test_yml_extension(self, tmp_path: Path) -> None:
        """File with .yml extension is parsed as YAML."""
        p = tmp_path / "test.yml"
        p.write_text("name: ymltest\n")
        result = confarg.load(WithDefaults, args=[], env={}, files=[p])
        assert result.name == "ymltest"

    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        """Unsupported file extension raises InvalidConfigFileError."""
        p = tmp_path / "test.ini"
        p.write_text("[section]\nkey = value")
        with pytest.raises(confarg.InvalidConfigFileError, match="Unsupported"):
            confarg.load(WithDefaults, args=[], env={}, files=[p])

    def test_nonexistent_config_file_raises(self) -> None:
        """Non-existent file raises InvalidConfigFileError."""
        with pytest.raises(confarg.InvalidConfigFileError, match="not found"):
            confarg.load(WithDefaults, args=[], env={}, files=[Path("/does_not_exist.toml")])


# ===========================================================================
# Expression edge cases
# ===========================================================================


class TestExpressionCornerCases:
    """Additional edge cases for expression resolution."""

    def test_expression_with_none_data(self) -> None:
        """None values in data don't break expression scanning."""
        data = {"a": None, "b": "${c}", "c": "hello"}
        resolved = resolve_expressions(data)
        assert resolved["a"] is None
        assert resolved["b"] == "hello"

    def test_expression_referencing_bool(self) -> None:
        """Expression can reference a boolean value."""
        data = {"flag": True, "result": "${flag}"}
        resolved = resolve_expressions(data)
        assert resolved["result"] is True

    def test_expression_referencing_int(self) -> None:
        """Expression preserves int type for pure ${expr}."""
        data = {"count": 42, "result": "${count}"}
        resolved = resolve_expressions(data)
        assert resolved["result"] == 42
        assert isinstance(resolved["result"], int)

    def test_expression_interpolation_stringifies(self) -> None:
        """Mixed text + ${expr} always produces a string."""
        data = {"count": 42, "msg": "count is ${count}"}
        resolved = resolve_expressions(data)
        assert resolved["msg"] == "count is 42"
        assert isinstance(resolved["msg"], str)

    def test_nested_escaped_expression(self) -> None:
        """Escaped $${...} produces literal ${...} in result."""
        data = {"a": "use $${VAR} in shell"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "use ${VAR} in shell"

    def test_expression_not_in_method(self) -> None:
        """Unary not operator in expression."""
        data = {"flag": True, "result": "${not flag}"}
        resolved = resolve_expressions(data)
        assert resolved["result"] is False

    def test_expression_chained_comparison(self) -> None:
        """Chained comparison like 1 < x < 10."""
        data = {"x": 5, "result": "${1 < x < 10}"}
        resolved = resolve_expressions(data)
        assert resolved["result"] is True

    def test_expression_subscript(self) -> None:
        """Subscript access in expression."""
        data = {"items": [10, 20, 30], "result": "${items[1]}"}
        resolved = resolve_expressions(data)
        assert resolved["result"] == 20

    def test_expression_float_literal(self) -> None:
        """Float literals in expressions must not be misinterpreted as list indices."""
        data = {"memory_gb": 16, "max_heap_size_mb": "${memory_gb * 1024 * 0.8}"}
        resolved = resolve_expressions(data)
        assert resolved["max_heap_size_mb"] == pytest.approx(16 * 1024 * 0.8)


# ===========================================================================
# Serialization edge cases
# ===========================================================================


class TestSerializationCornerCases:
    """Edge cases for dump/serialization."""

    def test_dump_with_none_optional(self) -> None:
        """dump() includes None for optional fields."""
        WithOptional = make_target("value", Optional[int], default=None)
        obj = WithOptional(value=None)
        result = confarg.dump(obj)
        assert "value" in result
        assert result["value"] is None

    def test_dump_with_enum_member(self) -> None:
        """Enum members serialize to their .value."""
        WithEnum = make_target("color", Color, default=Color.RED)
        obj = WithEnum(color=Color.BLUE)
        result = confarg.dump(obj)
        assert result["color"] == "blue"

    def test_dump_with_path(self) -> None:
        """Path serializes to string."""
        WithPath = make_target("location", Path, default=Path())
        obj = WithPath(location=Path("/tmp/test"))
        result = confarg.dump(obj)
        assert isinstance(result["location"], str)

    def test_dump_raw_dict(self) -> None:
        """dump() with a raw dict normalizes it (no error)."""
        from confarg._types import _StrToken

        data = {"key": _StrToken("value"), "count": 42}
        result = confarg.dump(data)
        assert result == {"key": "value", "count": 42}
        assert type(result["key"]) is str

    def test_dump_scalar_raises(self) -> None:
        """dump() with a non-dataclass, non-dict value raises TypeError."""
        with pytest.raises(TypeError, match="dataclass instance or dict"):
            confarg.dump(42)

    def test_dump_dataclass_class_raises(self) -> None:
        """dump() with a dataclass class (not instance) raises TypeError."""
        with pytest.raises(TypeError, match="instance"):
            confarg.dump(Flat)

    def test_roundtrip_toml_nested(self, tmp_path: Path) -> None:
        """Nested dataclass roundtrips through TOML correctly."""
        obj = AppConfig(
            db=DbConfig(host="h", port=1, name="n"),
            cache=CacheConfig(enabled=False, ttl=0),
            debug=True,
        )
        path = tmp_path / "out.toml"
        confarg.dump_file(obj, path)
        loaded = confarg.load(AppConfig, args=[], env={}, files=[path])
        assert loaded == obj

    def test_roundtrip_yaml_nested(self, tmp_path: Path) -> None:
        """Nested dataclass roundtrips through YAML correctly."""
        obj = AppConfig(
            db=DbConfig(host="h", port=1, name="n"),
            cache=CacheConfig(enabled=False, ttl=0),
            debug=True,
        )
        path = tmp_path / "out.yaml"
        confarg.dump_file(obj, path)
        loaded = confarg.load(AppConfig, args=[], env={}, files=[path])
        assert loaded == obj

    def test_dump_union_auto_tag_needed(self) -> None:
        """Ambiguous union adds class tag automatically."""
        obj = WithUnionAmbiguous(shape=CircleShape(x=1, y=2, radius=5))
        result = confarg.dump(obj)
        assert result["shape"]["class"] == "tests.conftest.CircleShape"

    def test_dump_union_auto_tag_not_needed(self) -> None:
        """Unambiguous union skips class tag."""
        obj = WithUnionDisjointDefaults(backend=PgConfig(host="h", port=5432, sslmode="require"))
        result = confarg.dump(obj)
        assert "class" not in result["backend"]


# ===========================================================================
# Multi-source priority edge cases
# ===========================================================================


class TestMergePriorityEdgeCases:
    """Edge cases for source priority merging."""

    def test_cli_overrides_config_nested(self, tmp_toml) -> None:
        """CLI overrides specific nested fields from config."""
        path = tmp_toml("""\
            [db]
            host = "config_host"
            port = 5432
            name = "config_db"
        """)
        result = confarg.load(
            AppConfig,
            args=["--db.host", "cli_host"],
            env={},
            files=[path],
        )
        assert result.db.host == "cli_host"
        assert result.db.port == 5432  # from config
        assert result.db.name == "config_db"  # from config

    def test_env_overrides_config_nested(self, tmp_toml) -> None:
        """Env overrides specific nested fields from config."""
        path = tmp_toml("""\
            [db]
            host = "config_host"
            port = 5432
            name = "config_db"
        """)
        result = confarg.load(
            AppConfig,
            args=[],
            env={"DB__PORT": "3306"},
            env_prefix="",
            files=[path],
        )
        assert result.db.host == "config_host"  # from config
        assert result.db.port == 3306  # from env
        assert result.db.name == "config_db"  # from config

    def test_all_three_sources_combined(self, tmp_toml) -> None:
        """Each source provides different fields."""
        path = tmp_toml("""\
            [db]
            host = "cfg_host"
            port = 9999
            name = "cfg_db"
        """)
        result = confarg.load(
            AppConfig,
            args=["--db.host", "cli_host", "--debug", "true"],
            env={"DB__PORT": "3306"},
            env_prefix="",
            files=[path],
        )
        assert result.db.host == "cli_host"  # CLI wins
        assert result.db.port == 3306  # env wins over config
        assert result.db.name == "cfg_db"  # config
        assert result.debug is True  # CLI


# ===========================================================================
# Env var edge cases
# ===========================================================================


class TestEnvVarCornerCases:
    """Additional env var parsing edge cases."""

    def test_env_empty_string_for_optional_str(self) -> None:
        """Empty env VALUE= for str|None gives empty string, not None."""
        WithOptionalStr = make_target("value", str | None, default=None)
        result = confarg.load(WithOptionalStr, args=[], env={"VALUE": ""}, env_prefix="")
        assert result.value == ""

    def test_env_empty_string_for_optional_int(self) -> None:
        """Empty env VALUE= for int|None raises (use VALUE__NONE= instead)."""
        WithOptionalInt = make_target("value", int | None, default=None)
        with pytest.raises(TypeCoercionError, match="To set this field to None"):
            confarg.load(WithOptionalInt, args=[], env={"VALUE": ""}, env_prefix="")

    def test_env_extra_vars_warn(self) -> None:
        """Extra env vars not matching fields emit ConfargWarning and are ignored."""
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = confarg.load(
                WithDefaults,
                args=[],
                env={"NAME": "ok", "NONEXISTENT_FIELD": "ignored"},
                env_prefix="",
            )
        assert result.name == "ok"
        assert any(
            "NONEXISTENT_FIELD" in str(w.message) for w in caught if issubclass(w.category, confarg.ConfargWarning)
        )

    def test_env_prefix_mismatch_ignored(self) -> None:
        """Env vars not matching prefix are ignored."""
        result = confarg.load(
            WithDefaults,
            args=[],
            env={"APP__NAME": "val", "NAME": "wrong"},
            env_prefix="APP",
        )
        assert result.name == "val"

    def test_env_nested_list_indexed(self) -> None:
        """Nested list from indexed env vars."""
        result = confarg.load(
            WithNestedList,
            args=[],
            env={
                "SERVERS__0__HOST": "a",
                "SERVERS__0__PORT": "1",
                "SERVERS__0__NAME": "db1",
            },
            env_prefix="",
        )
        assert len(result.servers) == 1
        assert result.servers[0].host == "a"


# ===========================================================================
# Dataclass with field(default_factory=...)
# ===========================================================================


class TestDefaultFactory:
    """Edge cases for fields with default_factory."""

    @pytest.mark.parametrize(
        ("tp", "factory", "field_name", "expected"),
        [
            (list[int], list, "items", []),
            (dict[str, int], dict, "mapping", {}),
            (set[str], set, "tags", set()),
        ],
        ids=["list", "dict", "set"],
    )
    def test_empty_default_factory(self, tp, factory, field_name, expected) -> None:
        """Test that an empty default_factory produces the correct empty collection."""
        target = make_target(field_name, tp, default_factory=factory)
        result = confarg.load(target, args=[], env={})
        assert getattr(result, field_name) == expected


# ===========================================================================
# Non-dataclass target edge cases
# ===========================================================================


class TestNonDataclassTargetCornerCases:
    """Edge cases for non-dataclass targets."""

    def test_int_from_env(self) -> None:
        """Plain int target from env var."""
        result = confarg.load(int, args=[], env={"VALUE": "42"}, env_prefix="", cli_prefix="confarg")
        assert result == 42

    def test_bool_from_cli_bare_flag(self) -> None:
        """Bool target with explicit value token."""
        result = confarg.load(bool, args=["--confarg", "true"], env={}, cli_prefix="confarg")
        assert result is True

    def test_missing_non_dataclass_raises(self) -> None:
        """Non-dataclass target with no data raises MissingFieldError."""
        with pytest.raises(confarg.MissingFieldError):
            confarg.load(int, args=[], env={}, cli_prefix="confarg")


# ===========================================================================
# Enum edge cases
# ===========================================================================


class TestEnumCornerCases:
    """Edge cases for enum coercion."""

    def test_enum_by_name(self) -> None:
        """Enum matched by member name when value doesn't match."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, args=["--color", "GREEN"], env={})
        assert result.color is Color.GREEN

    def test_enum_by_value(self) -> None:
        """Enum matched by member value."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, args=["--color", "blue"], env={})
        assert result.color is Color.BLUE

    def test_enum_invalid_value_raises(self) -> None:
        """Invalid enum value raises TypeCoercionError."""
        WithEnum = make_target("color", Color, default=Color.RED)
        with pytest.raises(confarg.TypeCoercionError):
            confarg.load(WithEnum, args=["--color", "purple"], env={})

    def test_enum_instance_passthrough(self) -> None:
        """Enum instance from TOML is passed through."""
        # When TOML gives us a string value, we coerce. When it gives us
        # a native value that matches, we pass through.
        result = _coerce_leaf(Color, Color.RED)
        assert result is Color.RED


# ===========================================================================
# Literal edge cases
# ===========================================================================


class TestLiteralCornerCases:
    """Edge cases for Literal type handling."""

    def test_literal_int(self) -> None:
        """Literal[1, 2, 3] from CLI."""
        WithLiteral = make_target("level", Literal[1, 2, 3], default=1)
        result = confarg.load(WithLiteral, args=["--level", "2"], env={})
        assert result.level == 2

    def test_literal_bool(self) -> None:
        """Literal[True, False] from CLI."""
        WithLiteral = make_target("flag", Literal[True, False], default=True)
        result = confarg.load(WithLiteral, args=["--flag", "False"], env={})
        assert result.flag is False

    def test_literal_mixed_types(self) -> None:
        """Literal['fast', 'slow', 1, 2] from CLI."""
        WithLiteral = make_target("mode", Literal["fast", "slow", 1, 2], default="fast")
        result = confarg.load(WithLiteral, args=["--mode", "2"], env={})
        assert result.mode == 2


# ===========================================================================
# Path edge cases
# ===========================================================================


class TestPathCornerCases:
    """Edge cases for Path type handling."""

    def test_path_with_spaces(self) -> None:
        """Path with spaces from CLI."""
        WithPath = make_target("location", Path, default=Path())
        result = confarg.load(WithPath, args=["--location", "/path/with spaces/file"], env={})
        assert result.location == Path("/path/with spaces/file")

    def test_path_relative(self) -> None:
        """Relative path from CLI."""
        WithPath = make_target("location", Path, default=Path())
        result = confarg.load(WithPath, args=["--location", "./relative/path"], env={})
        assert result.location == Path("./relative/path")


# ===========================================================================
# Multiple config files
# ===========================================================================


class TestMultipleConfigFilesCornerCases:
    """Edge cases for multiple config file loading."""

    def test_cli_config_and_files_param_combined(self, tmp_toml) -> None:
        """Both files= param and --config flag merge correctly."""
        p1 = tmp_toml("name = 'from_files'\ncount = 1\nrate = 0.0\nverbose = false\n", "base.toml")
        p2 = tmp_toml("name = 'from_cli_config'\n", "override.toml")
        result = confarg.load(
            Flat,
            args=["--config", str(p2)],
            env={},
            files=[p1],
        )
        # --config files are merged after files= files
        assert result.name == "from_cli_config"
        assert result.count == 1  # from files= file

    def test_multiple_cli_config_flags(self, tmp_toml) -> None:
        """Multiple --config flags are all loaded and merged."""
        p1 = tmp_toml("name = 'a'\ncount = 1\nrate = 0.0\nverbose = false\n", "a.toml")
        p2 = tmp_toml("name = 'b'\n", "b.toml")
        result = confarg.load(
            Flat,
            args=["--config", str(p1), "--config", str(p2)],
            env={},
        )
        assert result.name == "b"
        assert result.count == 1


# ===========================================================================
# union_tag parameter
# ===========================================================================


class TestUnionTagParameter:
    """The union_tag parameter for custom discriminator field names."""

    def test_custom_union_tag_load(self) -> None:
        """Custom union_tag='type' in load()."""
        result = confarg.load(
            WithUnionAmbiguous,
            args=[
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

    def test_custom_union_tag_dump(self) -> None:
        """Custom union_tag='type' in dump()."""
        obj = WithUnionAmbiguous(shape=CircleShape(x=1, y=2, radius=5))
        result = confarg.dump(obj, union_tag="type", tag_policy="always")
        assert result["shape"]["type"] == "tests.conftest.CircleShape"
        assert "class" not in result["shape"]

    def test_custom_union_tag_roundtrip(self, tmp_path: Path) -> None:
        """Roundtrip with custom union_tag through TOML."""
        obj = WithUnionAmbiguous(shape=SquareShape(x=0, y=0, radius=3))
        path = tmp_path / "out.toml"
        confarg.dump_file(obj, path, union_tag="kind")
        loaded = confarg.load(WithUnionAmbiguous, args=[], env={}, files=[path], union_tag="kind")
        assert isinstance(loaded.shape, SquareShape)
        assert loaded.shape.radius == pytest.approx(3.0)


# ===========================================================================
# Non-union base class dispatch via class tag
# ===========================================================================


@dataclass
class _AnimalBase:
    pass


@dataclass
class _Dog(_AnimalBase):
    name: str
    breed: str


@dataclass
class _Cat(_AnimalBase):
    name: str
    indoor: bool = True


class TestNonUnionClassTagDispatch:
    """Base-class dispatch via the class: tag (no Union involved).

    Exercises the _construct_by_class_path branch in construct() that fires
    when the target is a plain struct (not a Union) but the data dict contains
    the union_tag key.  This is how the 03_inheritance example works.
    """

    def test_from_dict_dispatches_to_subclass(self) -> None:
        """Test that from_dict dispatches to the correct subclass via class tag."""
        result = confarg.from_dict(
            _AnimalBase,
            {"class": "tests.test_corner_cases._Dog", "name": "Rex", "breed": "Labrador"},
        )
        assert isinstance(result, _Dog)
        assert result.name == "Rex"
        assert result.breed == "Labrador"

    def test_load_from_yaml_dispatches_to_subclass(self, tmp_yaml) -> None:
        """Test that load from YAML dispatches to the correct subclass via class tag."""
        path = tmp_yaml("""\
            class: tests.test_corner_cases._Cat
            name: Whiskers
            indoor: false
        """)
        result = confarg.load(_AnimalBase, args=[], env={}, files=[path])
        assert isinstance(result, _Cat)
        assert result.name == "Whiskers"
        assert result.indoor is False

    def test_wrong_subclass_raises(self) -> None:
        """A class that is not a subclass of the target raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="not a subclass"):
            confarg.from_dict(
                _Dog,
                {"class": "tests.test_corner_cases._Cat", "name": "Whiskers"},
            )


# ===========================================================================
# Empty dataclass and minimal configs
# ===========================================================================


class TestEmptyDataclassCornerCases:
    """Edge cases for empty or minimal dataclass configurations."""

    def test_empty_dataclass_from_all_sources(self, tmp_toml) -> None:
        """Empty dataclass loaded from all three sources."""
        path = tmp_toml("")
        result = confarg.load(Empty, args=[], env={}, files=[path])
        assert isinstance(result, Empty)

    def test_dataclass_single_field(self) -> None:
        """Dataclass with a single required field."""
        WithSingle = make_target("value", int)
        result = confarg.load(WithSingle, args=["--value", "42"], env={})
        assert result.value == 42


# ===========================================================================
# __post_init__ support
# ===========================================================================


@dataclass
class _WithPostInit:
    foo: str
    bar: str | None = None

    def __post_init__(self) -> None:
        if self.bar is None:
            self.bar = self.foo


class TestPostInit:
    """__post_init__ is invoked after construction."""

    def test_post_init_sets_bar_from_foo_when_bar_absent(self) -> None:
        """When bar is not provided, __post_init__ copies foo into bar."""
        result = confarg.load(_WithPostInit, args=["--foo", "hello"], env={})
        assert result.foo == "hello"
        assert result.bar == "hello"

    def test_post_init_does_not_override_explicit_bar(self) -> None:
        """When bar is provided explicitly, __post_init__ leaves it alone."""
        result = confarg.load(_WithPostInit, args=["--foo", "hello", "--bar", "world"], env={})
        assert result.foo == "hello"
        assert result.bar == "world"


# ===========================================================================
# _is_set / _is_frozenset consistency (Fix #1)
# ===========================================================================


class TestIsSetFrozensetConsistency:
    """Verify _is_set only matches set, _is_frozenset only matches frozenset."""

    @pytest.mark.parametrize(
        ("fn", "tp", "expected"),
        [
            (_is_set, set[int], True),
            (_is_set, frozenset[int], False),
            (_is_frozenset, frozenset[int], True),
            (_is_frozenset, set[int], False),
        ],
        ids=["set-set", "set-frozenset", "frozenset-frozenset", "frozenset-set"],
    )
    def test_type_predicate(self, fn, tp, expected) -> None:
        """Test that type predicate functions return correct results."""
        assert fn(tp) is expected

    def test_frozenset_still_works_end_to_end(self) -> None:
        """Frozenset field still works correctly after _is_set fix."""
        WithFrozenSet = make_target("tags", frozenset[str], default_factory=frozenset)
        result = confarg.load(WithFrozenSet, args=["--tags", "a", "b"], env={})
        assert result.tags == frozenset({"a", "b"})

    def test_frozenset_roundtrip(self, tmp_path: Path) -> None:
        """Frozenset serializes and deserializes correctly."""
        WithFrozenSet = make_target("tags", frozenset[str], default_factory=frozenset)
        obj = WithFrozenSet(tags=frozenset({"x", "y", "z"}))
        result = confarg.dump(obj)
        assert sorted(result["tags"]) == ["x", "y", "z"]


# ===========================================================================
# Silent failure fixes — all cases that previously swallowed errors
# ===========================================================================


class TestSilentFailureFixes:
    """Previously-silent errors that now raise TypeCoercionError with a clear message."""

    # --- Union: exhausted leaf variants ---

    @pytest.mark.parametrize(
        ("type_ann", "env_val", "match"),
        [
            (Union[int, float, None], "xyz", r"Cannot coerce.*int.*float.*None"),
            (Union[int, float, None], "not_a_number", r"'value'"),
            (Union[bool, int, None], "abc", "Cannot coerce"),
        ],
        ids=["int-float-none-uncoercible", "int-float-none-path", "bool-int-none"],
    )
    def test_union_exhausted_raises(self, type_ann, env_val, match) -> None:
        """Test that an uncoercible union value raises TypeCoercionError."""
        WithUnion = make_target("value", type_ann, default=None)
        with pytest.raises(TypeCoercionError, match=match):
            confarg.load(WithUnion, args=[], env={"VALUE": env_val}, env_prefix="")

    def test_union_int_float_none_empty_string_raises(self) -> None:
        """Union[int, float, None]: empty string raises (use VALUE__NONE= instead)."""
        WithUnion = make_target("value", int | float | None, default=None)
        with pytest.raises(TypeCoercionError):
            confarg.load(WithUnion, args=[], env={"VALUE": ""}, env_prefix="")

    def test_union_int_float_none_valid_int_still_works(self) -> None:
        """Test that a valid int still works in a Union[int, float, None]."""
        WithUnion = make_target("value", int | float | None, default=None)
        result = confarg.load(WithUnion, args=[], env={"VALUE": "42"}, env_prefix="")
        assert result.value == 42
        assert isinstance(result.value, int)

    # --- wrong data type raises TypeCoercionError ---

    @pytest.mark.parametrize(
        ("tp", "bad_value", "match"),
        [
            (list[int], "1 2 3", "expected list or dict"),
            (list[int], 42, "expected list or dict"),
            (dict[str, int], "key=val", "expected dict"),
            (dict[str, int], [1, 2, 3], "expected dict"),
            (set[int], "1 2 3", "expected sequence or dict"),
            (frozenset[str], 42, "expected sequence or dict"),
            (tuple[str, int], "hello 1", "expected list, tuple, or dict"),
            (tuple[str, int], None, "expected list, tuple, or dict"),
            (tuple[int, ...], "1 2 3", "expected sequence or dict"),
            (DbConfig, "not_a_dict", "expected dict"),
            (DbConfig, None, "expected dict"),
        ],
        ids=[
            "list-str",
            "list-int",
            "dict-str",
            "dict-list",
            "set-str",
            "frozenset-int",
            "tuple-fixed-str",
            "tuple-fixed-none",
            "tuple-varlen-str",
            "dc-str",
            "dc-none",
        ],
    )
    def test_wrong_type_raises(self, tp, bad_value, match) -> None:
        """Test that constructing with a wrong type raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match=match):
            construct(tp, bad_value, path="field")

    @pytest.mark.parametrize(
        ("tp", "bad_value", "path", "match"),
        [
            (list[str], "wrong", "tags", r"'tags'"),
            (dict[str, str], 99, "cfg", r"'cfg'"),
            (DbConfig, "wrong", "db", r"DbConfig.*'db'"),
        ],
        ids=["list-path", "dict-path", "dc-path"],
    )
    def test_error_contains_path(self, tp, bad_value, path, match) -> None:
        """Test that TypeCoercionError message contains the field path."""
        with pytest.raises(TypeCoercionError, match=match):
            construct(tp, bad_value, path=path)


# ===========================================================================
# *args and **kwargs support in plain classes
# ===========================================================================


class TestVarParams:
    """Plain classes with *args and/or **kwargs in __init__."""

    def test_var_keyword_only(self) -> None:
        """Test that a class with only **kwargs is constructed correctly."""

        class KwOnly:
            def __init__(self, **options: int) -> None:
                self.options = options

        result = confarg.from_dict(KwOnly, {"options": {"a": 1, "b": 2}})
        assert result.options == {"a": 1, "b": 2}

    def test_var_keyword_respects_annotation(self) -> None:
        """Test that **kwargs with type annotation coerces values correctly."""

        class KwTyped:
            def __init__(self, **opts: int) -> None:
                self.opts = opts

        result = confarg.from_dict(KwTyped, {"opts": {"x": _StrToken("42")}})
        assert result.opts == {"x": 42}

    def test_var_positional_only(self) -> None:
        """Test that a class with only *args is constructed correctly."""

        class Positional:
            def __init__(self, *items: str) -> None:
                self.items = items

        result = confarg.from_dict(Positional, {"items": ["a", "b", "c"]})
        assert result.items == ("a", "b", "c")

    def test_var_positional_respects_annotation(self) -> None:
        """Test that *args with type annotation coerces values correctly."""

        class Nums:
            def __init__(self, *values: int) -> None:
                self.values = values

        result = confarg.from_dict(Nums, {"values": [_StrToken("1"), _StrToken("2"), _StrToken("3")]})
        assert result.values == (1, 2, 3)

    def test_named_and_var_positional(self) -> None:
        """Test that named params and *args are both handled correctly."""

        class Tagged:
            def __init__(self, host: str, *tags: str) -> None:
                self.host = host
                self.tags = tags

        result = confarg.from_dict(Tagged, {"host": "localhost", "tags": ["web", "db"]})
        assert result.host == "localhost"
        assert result.tags == ("web", "db")

    def test_named_and_var_keyword(self) -> None:
        """Test that named params and **kwargs are both handled correctly."""

        class Server:
            def __init__(self, host: str, **options: int) -> None:
                self.host = host
                self.options = options

        result = confarg.from_dict(Server, {"host": "localhost", "options": {"port": 8080}})
        assert result.host == "localhost"
        assert result.options == {"port": 8080}

    def test_all_three(self) -> None:
        """Test that named, *args, and **kwargs are all handled together."""

        class Mixed:
            def __init__(self, name: str, *args: int, **kwargs: str) -> None:
                self.name = name
                self.args = args
                self.kwargs = kwargs

        result = confarg.from_dict(Mixed, {"name": "x", "args": [1, 2], "kwargs": {"a": "b"}})
        assert result.name == "x"
        assert result.args == (1, 2)
        assert result.kwargs == {"a": "b"}

    def test_non_standard_names(self) -> None:
        """Test that non-standard *args/**kwargs names work correctly."""

        class Custom:
            def __init__(self, *tags: str, **extra: float) -> None:
                self.tags = tags
                self.extra = extra

        result = confarg.from_dict(Custom, {"tags": ["x"], "extra": {"rate": math.pi}})
        assert result.tags == ("x",)
        assert result.extra == pytest.approx({"rate": math.pi})

    def test_defaults_when_omitted(self) -> None:
        """Test that default values are used when var params are omitted from dict."""

        class WithDefaults:
            def __init__(self, name: str = "anon", *args: int, **kwargs: str) -> None:
                self.name = name
                self.args = args
                self.kwargs = kwargs

        result = confarg.from_dict(WithDefaults, {})
        assert result.name == "anon"
        assert result.args == ()
        assert result.kwargs == {}

    def test_unknown_field_still_raises(self) -> None:
        """Test that an unknown top-level field still raises TypeCoercionError."""

        class Simple:
            def __init__(self, **opts: int) -> None:
                self.opts = opts

        with pytest.raises(TypeCoercionError, match="Unknown field"):
            confarg.from_dict(Simple, {"not_a_field": 1})

    def test_construction_from_dict(self) -> None:
        """Test that a plain class with mixed var params is constructed from a raw dict."""

        class Stored:
            def __init__(self, x: int, *items: str, **meta: float) -> None:
                self.x = x
                self.items = items
                self.meta = meta

        raw = {"x": 5, "items": ["a", "b"], "meta": {"pi": math.pi}}
        obj = confarg.from_dict(Stored, raw)
        assert obj.x == 5
        assert list(obj.items) == ["a", "b"]
        # Plain classes: dump the raw dict, not the object
        with pytest.raises(TypeError, match="plain class"):
            confarg.dump(obj)


# ===========================================================================
# Union type-switch: class tag in override discards base
# ===========================================================================


class TestUnionTypeSwitchViaClassTag:
    """When the override dict carries the union_tag, the base is discarded entirely.

    This prevents fields from a previously-loaded union variant from contaminating
    an override that switches to a different variant.
    """

    def test_deep_merge_discards_base_when_override_has_union_tag(self) -> None:
        """Test that _deep_merge discards the base when the override has a union_tag."""
        base = {"host": "prod", "port": 5432, "name": "mydb"}
        override = {"class": "tests.test_corner_cases._SqliteVariant", "dbpath": "db.sqlite"}
        result = _deep_merge(base, override, union_tag="class")
        assert result == override

    def test_deep_merge_normal_merge_when_no_union_tag(self) -> None:
        """Test that _deep_merge performs a normal merge when no union_tag is present."""
        base = {"host": "prod", "port": 5432, "name": "mydb"}
        override = {"port": 9999}
        result = _deep_merge(base, override, union_tag="class")
        assert result == {"host": "prod", "port": 9999, "name": "mydb"}

    def test_deep_merge_nested_discard(self) -> None:
        """Test that _deep_merge discards a nested base when a nested override has a union_tag."""
        base = {"db": {"host": "prod", "port": 5432, "name": "mydb"}}
        override = {"db": {"class": "tests.test_corner_cases._SqliteVariant", "dbpath": "x.sqlite"}}
        result = _deep_merge(base, override, union_tag="class")
        assert result == {"db": {"class": "tests.test_corner_cases._SqliteVariant", "dbpath": "x.sqlite"}}

    def test_load_cross_type_switch_via_config_file_and_cli(self, tmp_yaml) -> None:
        """Test that switching union type via CLI class tag overrides a config file variant."""
        path = tmp_yaml("host: example.com\nname: mydb\nport: 1234\n")
        result = confarg.load(
            _SqliteVariant | _ServerVariant,
            args=[
                "--config",
                str(path),
                "--class",
                "tests.test_corner_cases._SqliteVariant",
                "--dbpath",
                "db.sqlite",
            ],
            env={},
        )
        assert isinstance(result, _SqliteVariant)
        assert result.dbpath == "db.sqlite"

    def test_load_partial_override_same_type_without_repeating_class(self, tmp_yaml) -> None:
        """Test that partial override of same union type works without repeating class tag."""
        path = tmp_yaml(
            "class: tests.test_corner_cases._ServerVariant\nhost: prod.example.com\nport: 5432\nname: mydb\n"
        )
        result = confarg.load(
            _SqliteVariant | _ServerVariant,
            args=["--config", str(path), "--host", "localhost"],
            env={},
        )
        assert isinstance(result, _ServerVariant)
        assert result.host == "localhost"
        assert result.port == 5432
        assert result.name == "mydb"

    def test_deep_merge_three_way_priority_with_type_switch(self) -> None:
        """Test three-way deep_merge priority where a higher-priority override switches union type."""
        # Simulate: file provides ServerVariant fields, env provides nothing,
        # then a second override (e.g., from a higher-priority config) introduces
        # a class tag and SqliteVariant fields.
        file_data = {"host": "prod", "port": 5432, "name": "mydb"}
        override = {"class": "tests.test_corner_cases._SqliteVariant", "dbpath": "override.sqlite"}
        merged = _deep_merge(file_data, override, union_tag="class")
        # The class tag in the override discards the ServerVariant fields entirely.
        assert merged == override

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for CLI argument parsing: dot-separated args, prefix, --flag/--no-flag, collections, config flag."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

import confarg
from tests.conftest import (
    AppConfig,
    Color,
    DbConfig,
    DeepNested,
    Flat,
    WithCollections,
    WithDefaults,
    WithNestedList,
    WithOptionalNested,
    make_target,
)

# ---------------------------------------------------------------------------
# Basic CLI parsing
# ---------------------------------------------------------------------------


class TestCliBasic:
    """Basic CLI argument parsing."""

    def test_flat_all_fields(self) -> None:
        """All flat fields from CLI."""
        result = confarg.load(
            Flat,
            args=["--name", "hi", "--count", "5", "--rate", "1.5", "--verbose", "true"],
            env={},
        )
        assert result.name == "hi"
        assert result.count == 5
        assert result.rate == pytest.approx(1.5)
        assert result.verbose is True

    def test_defaults_no_args(self) -> None:
        """All defaults used when args=[] and env={}."""
        result = confarg.load(WithDefaults, args=[], env={})
        assert result.name == "default"
        assert result.count == 0

    def test_partial_override(self) -> None:
        """Only some fields overridden, rest use defaults."""
        result = confarg.load(WithDefaults, args=["--name", "custom"], env={})
        assert result.name == "custom"
        assert result.count == 0


# ---------------------------------------------------------------------------
# Dot-separated nested args
# ---------------------------------------------------------------------------


class TestCliDotSeparated:
    """Dot-separated paths for nested dataclass fields."""

    def test_nested_dot_path(self) -> None:
        """Parse nested fields via dot-separated CLI args."""
        result = confarg.load(
            AppConfig,
            args=["--db.host", "h", "--db.port", "1", "--db.name", "n"],
            env={},
        )
        assert result.db.host == "h"
        assert result.db.port == 1

    def test_deep_nested_dot_path(self) -> None:
        """Three levels of nesting with dots."""
        result = confarg.load(
            DeepNested,
            args=["--app.db.host", "h", "--app.db.port", "1", "--app.db.name", "n"],
            env={},
        )
        assert result.app.db.host == "h"

    def test_nested_override_defaults(self) -> None:
        """Override a default on a nested dataclass."""
        result = confarg.load(
            AppConfig,
            args=[
                "--db.host",
                "h",
                "--db.port",
                "1",
                "--db.name",
                "n",
                "--cache.ttl",
                "60",
            ],
            env={},
        )
        assert result.cache.ttl == 60
        assert result.cache.enabled is True  # default kept


# ---------------------------------------------------------------------------
# CLI prefix
# ---------------------------------------------------------------------------


class TestCliPrefix:
    """CLI prefix support."""

    def test_prefix_flat(self) -> None:
        """Flat field with CLI prefix."""
        result = confarg.load(WithDefaults, args=["--app.name", "val"], env={}, cli_prefix="app")
        assert result.name == "val"

    def test_prefix_nested(self) -> None:
        """Nested field with CLI prefix."""
        result = confarg.load(
            AppConfig,
            args=["--cfg.db.host", "h", "--cfg.db.port", "1", "--cfg.db.name", "n"],
            env={},
            cli_prefix="cfg",
        )
        assert result.db.host == "h"

    def test_prefix_does_not_match_without_prefix(self) -> None:
        """Args without the prefix are not recognized."""
        with pytest.raises(confarg.ConfargError):
            confarg.load(
                Flat,
                args=["--name", "x", "--count", "1", "--rate", "0", "--verbose", "true"],
                env={},
                cli_prefix="app",
            )


# ---------------------------------------------------------------------------
# Boolean value tokens (--flag true / --flag false)
# ---------------------------------------------------------------------------


class TestCliBoolValueToken:
    """Boolean fields set via explicit value tokens."""

    @pytest.mark.parametrize("token", ["true", "True", "TRUE", "1", "yes", "on"])
    def test_truthy_tokens(self, token: str) -> None:
        result = confarg.load(WithDefaults, args=["--verbose", token], env={})
        assert result.verbose is True

    @pytest.mark.parametrize("token", ["false", "False", "FALSE", "0", "no", "off"])
    def test_falsy_tokens(self, token: str) -> None:
        result = confarg.load(WithDefaults, args=["--verbose", token], env={})
        assert result.verbose is False

    def test_nested_bool_true(self) -> None:
        result = confarg.load(
            AppConfig,
            args=["--db.host", "h", "--db.port", "1", "--db.name", "n", "--debug", "true"],
            env={},
        )
        assert result.debug is True

    def test_nested_bool_false(self) -> None:
        result = confarg.load(
            AppConfig,
            args=["--db.host", "h", "--db.port", "1", "--db.name", "n", "--cache.enabled", "false"],
            env={},
        )
        assert result.cache.enabled is False

    def test_optional_bool_none(self) -> None:
        WithOptBool = make_target("flag", bool | None, default=None)
        result = confarg.load(WithOptBool, args=["--flag", "none"], env={})
        assert result.flag is None

    def test_bool_missing_value_raises(self) -> None:
        with pytest.raises(confarg.ConfargError, match="Missing value"):
            confarg.load(WithDefaults, args=["--verbose"], env={})

    def test_trailing_dot_raises_missing_field_name(self) -> None:
        """--foo. (trailing dot) should say 'Missing field name after' not 'not found'."""
        with pytest.raises(confarg.UnknownArgumentError, match="Missing field name after '--name.'"):
            confarg.load(WithDefaults, args=["--name."], env={})

    def test_misplaced_append_plus_raises_missing_field_name(self) -> None:
        """--foo.+ (dot before +) should give the same error as --foo. (trailing dot)."""
        with pytest.raises(confarg.UnknownArgumentError, match="Missing field name after '--name.'"):
            confarg.load(WithDefaults, args=["--name.+"], env={})


# ---------------------------------------------------------------------------
# Collections from CLI
# ---------------------------------------------------------------------------


class TestCliCollections:
    """Collection types from CLI args."""

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
                make_target("tags", set[str], default_factory=set),
                ["--tags", "a", "b"],
                "tags",
                {"a", "b"},
            ),
        ],
        ids=["list", "set"],
    )
    def test_single_collection(self, target_cls, args, field, expected) -> None:
        """Parse a single collection from space-separated CLI values."""
        result = confarg.load(target_cls, args=args, env={})
        assert getattr(result, field) == expected

    def test_list_indexed(self) -> None:
        """List from indexed args."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, args=["--items.0", "10", "--items.1", "20"], env={})
        assert result.items == [10, 20]

    def test_tuple_positional(self) -> None:
        """Tuple from positional values."""
        WithTuple = make_target("pair", tuple[str, int], default=("", 0))
        result = confarg.load(WithTuple, args=["--pair", "x", "7"], env={})
        assert result.pair == ("x", 7)

    def test_dict_keyed(self) -> None:
        """Dict from keyed args."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        result = confarg.load(WithDict, args=["--metadata.k1", "1", "--metadata.k2", "2"], env={})
        assert result.metadata == {"k1": 1, "k2": 2}

    def test_multiple_collections(self) -> None:
        """Multiple collection fields in one call."""
        result = confarg.load(
            WithCollections,
            args=[
                "--names",
                "a",
                "b",
                "--tags",
                "t1",
                "--mapping.k",
                "5",
            ],
            env={},
        )
        assert result.names == ["a", "b"]
        assert result.tags == {"t1"}
        assert result.mapping == {"k": 5}


# ---------------------------------------------------------------------------
# Config flag
# ---------------------------------------------------------------------------


class TestCliConfigFlag:
    """The --config flag for specifying config files."""

    def test_config_flag_loads_toml(self, tmp_toml) -> None:
        """--config loads a TOML file."""
        path = tmp_toml("""\
            name = "from_file"
            count = 10
            rate = 2.5
            verbose = true
        """)
        result = confarg.load(Flat, args=["--config", str(path)], env={})
        assert result.name == "from_file"
        assert result.count == 10

    def test_config_flag_loads_yaml(self, tmp_yaml) -> None:
        """--config loads a YAML file."""
        path = tmp_yaml("""\
            name: from_yaml
            count: 7
            rate: 0.5
            verbose: false
        """)
        result = confarg.load(Flat, args=["--config", str(path)], env={})
        assert result.name == "from_yaml"

    def test_config_flag_subpath(self, tmp_toml) -> None:
        """--config.db targets a sub-path in a TOML file."""
        path = tmp_toml("""\
            host = "confighost"
            port = 9999
            name = "configdb"
        """)
        result = confarg.load(
            AppConfig,
            args=["--config.db", str(path)],
            env={},
        )
        assert result.db.host == "confighost"
        assert result.db.port == 9999

    def test_custom_config_flag_name(self, tmp_toml) -> None:
        """Custom config flag name via config_flag parameter."""
        path = tmp_toml("""\
            name = "custom"
            count = 1
            rate = 0.0
            verbose = false
        """)
        result = confarg.load(Flat, args=["--cfg", str(path)], env={}, config_flag="cfg")
        assert result.name == "custom"

    def test_multiple_config_files(self, tmp_toml) -> None:
        """Later config files override earlier ones."""
        path1 = tmp_toml("name = 'first'\ncount = 1\nrate = 0.0\nverbose = false\n", "a.toml")
        path2 = tmp_toml("name = 'second'\ncount = 2\nrate = 0.0\nverbose = false\n", "b.toml")
        result = confarg.load(
            Flat,
            args=["--config", str(path1), "--config", str(path2)],
            env={},
        )
        assert result.name == "second"
        assert result.count == 2


# ---------------------------------------------------------------------------
# --key=value inline syntax
# ---------------------------------------------------------------------------


class TestCliEqualsSign:
    """The --key=value form (equals sign instead of space)."""

    def test_flat_field_equals(self) -> None:
        """--name=hello sets name."""
        result = confarg.load(Flat, args=["--name=hi", "--count=3", "--rate=1.5", "--verbose=true"], env={})
        assert result.name == "hi"
        assert result.count == 3
        assert result.rate == pytest.approx(1.5)
        assert result.verbose is True

    def test_nested_field_equals(self) -> None:
        """--db.host=h sets nested field."""
        result = confarg.load(
            AppConfig,
            args=["--db.host=myhost", "--db.port=5432", "--db.name=mydb"],
            env={},
        )
        assert result.db.host == "myhost"
        assert result.db.port == 5432

    def test_config_flag_equals(self, tmp_toml) -> None:
        """--config=path.toml loads the config file."""
        path = tmp_toml("name = 'from_eq'\ncount = 7\nrate = 0.0\nverbose = false\n")
        result = confarg.load(Flat, args=[f"--config={path}"], env={})
        assert result.name == "from_eq"
        assert result.count == 7

    def test_mixed_equals_and_space(self) -> None:
        """Mix of --key=value and --key value in the same args list."""
        result = confarg.load(Flat, args=["--name=mixed", "--count", "9", "--rate=0.1", "--verbose=true"], env={})
        assert result.name == "mixed"
        assert result.count == 9
        assert result.rate == pytest.approx(0.1)

    def test_value_containing_equals(self) -> None:
        """Value itself contains an equals sign (only the first = is the separator)."""
        result = confarg.load(Flat, args=["--name=a=b", "--count=0", "--rate=0.0", "--verbose=true"], env={})
        assert result.name == "a=b"


# ---------------------------------------------------------------------------
# CLI args disabled
# ---------------------------------------------------------------------------


class TestCliDisabled:
    """CLI parsing disabled via empty list."""

    def test_empty_args_list(self) -> None:
        """args=[] means no CLI parsing."""
        result = confarg.load(WithDefaults, args=[], env={})
        assert result.name == "default"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestCliEdgeCases:
    """Edge cases for CLI parsing."""

    def test_value_starting_with_dash(self) -> None:
        """A value starting with a dash (negative number) is not treated as a flag."""
        result = confarg.load(
            Flat,
            args=["--name", "x", "--count", "-5", "--rate", "-1.5", "--verbose", "true"],
            env={},
        )
        assert result.count == -5
        assert result.rate == pytest.approx(-1.5)

    def test_enum_from_cli(self) -> None:
        """Enum value from CLI."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, args=["--color", "blue"], env={})
        assert result.color is Color.BLUE

    def test_path_from_cli(self) -> None:
        """Path from CLI."""
        WithPath = make_target("location", Path, default=Path())
        result = confarg.load(WithPath, args=["--location", "/a/b"], env={})
        assert result.location == Path("/a/b")

    @pytest.mark.parametrize(
        "target_cls",
        [
            make_target("value", Optional[int], default=None),
            make_target("value", int | None, default=None),
        ],
        ids=["Optional[int]", "int|None"],
    )
    def test_optional_from_cli(self, target_cls) -> None:
        """Optional/pipe-none value from CLI."""
        result = confarg.load(target_cls, args=["--value", "42"], env={})
        assert result.value == 42

    def test_optional_str_none_token_gives_python_none(self) -> None:
        """--value none for str | None gives Python None (steal rule)."""
        WithOptionalStr = make_target("value", str | None, default="hello")
        result = confarg.load(WithOptionalStr, args=["--value", "none"], env={})
        assert result.value is None

    def test_missing_value_for_str_field_raises(self) -> None:
        """--field with no following value raises ConfargError instead of silently skipping."""
        from confarg._errors import ConfargError

        WithStr = make_target("name", str)
        with pytest.raises(ConfargError, match="Missing value for '--name'"):
            confarg.load(WithStr, args=["--name"], env={})

    def test_missing_value_when_next_is_flag_raises(self) -> None:
        """--field followed immediately by another flag raises ConfargError."""
        from confarg._errors import ConfargError

        make_target("name", str)
        make_target("verbose", bool, default=False)
        from dataclasses import make_dataclass

        Both = make_dataclass("Both", [("name", str), ("verbose", bool, field(default=False))])
        with pytest.raises(ConfargError, match="Missing value for '--name'"):
            confarg.load(Both, args=["--name", "--verbose"], env={})

    def test_missing_value_for_int_field_raises(self) -> None:
        """--field with no following value raises for int fields too."""
        from confarg._errors import ConfargError

        WithInt = make_target("count", int)
        with pytest.raises(ConfargError, match="Missing value for '--count'"):
            confarg.load(WithInt, args=["--count"], env={})


# ---------------------------------------------------------------------------
# None via value token (--field none / --field null)
# ---------------------------------------------------------------------------


class TestCliNoneToken:
    """Optional fields set to None by passing 'none' or 'null' as the value."""

    @pytest.mark.parametrize(
        "target_cls",
        [
            make_target("value", Optional[int], default=99),
            make_target("value", int | None, default=99),
            make_target("value", float | None, default=1.5),
        ],
        ids=["Optional[int]", "int|None", "float|None"],
    )
    @pytest.mark.parametrize("token", ["none", "None", "NONE", "null", "Null", "NULL"])
    def test_none_token_sets_optional_to_none(self, target_cls, token: str) -> None:
        result = confarg.load(target_cls, args=["--value", token], env={})
        assert result.value is None

    def test_optional_str_none_token(self) -> None:
        """'none' in str | None yields Python None (steal rule)."""
        WithOpt = make_target("value", str | None, default="hello")
        result = confarg.load(WithOpt, args=["--value", "none"], env={})
        assert result.value is None

    def test_nested_optional_field(self) -> None:
        from dataclasses import make_dataclass

        Inner = make_dataclass("Inner", [("x", int, field(default=1))])
        Outer = make_dataclass("Outer", [("inner", Inner | None, field(default=None))])
        result = confarg.load(Outer, args=["--inner", "none"], env={})
        assert result.inner is None

    def test_none_followed_by_next_flag(self) -> None:
        """'none' token is consumed; next flag is parsed normally."""
        from dataclasses import make_dataclass

        Both = make_dataclass(
            "Both",
            [
                ("value", int | None, field(default=99)),
                ("other", str, field(default="x")),
            ],
        )
        result = confarg.load(Both, args=["--value", "none", "--other", "hello"], env={})
        assert result.value is None
        assert result.other == "hello"


# ---------------------------------------------------------------------------
# Steal rule for str unions
# ---------------------------------------------------------------------------


class TestCliStealRule:
    """When str is in a union, non-str types steal their natural string forms."""

    def test_str_none_none_token(self) -> None:
        T = make_target("v", str | None, default="x")
        assert confarg.load(T, args=["--v", "none"], env={}).v is None

    def test_str_none_null_token(self) -> None:
        T = make_target("v", str | None, default="x")
        assert confarg.load(T, args=["--v", "null"], env={}).v is None

    def test_str_float_inf(self) -> None:
        T = make_target("v", str | float, default=0.0)
        assert confarg.load(T, args=["--v", "inf"], env={}).v == float("inf")

    def test_str_float_plus_inf(self) -> None:
        T = make_target("v", str | float, default=0.0)
        assert confarg.load(T, args=["--v", "+inf"], env={}).v == float("inf")

    def test_str_float_minus_inf(self) -> None:
        T = make_target("v", str | float, default=0.0)
        import math

        assert math.isinf(confarg.load(T, args=["--v", "-inf"], env={}).v)

    def test_str_float_nan(self) -> None:
        import math

        T = make_target("v", str | float, default=0.0)
        assert math.isnan(confarg.load(T, args=["--v", "nan"], env={}).v)

    def test_str_bool_true(self) -> None:
        T = make_target("v", str | bool, default=False)
        assert confarg.load(T, args=["--v", "true"], env={}).v is True

    def test_str_bool_false(self) -> None:
        T = make_target("v", str | bool, default=True)
        assert confarg.load(T, args=["--v", "false"], env={}).v is False

    def test_str_float_decimal(self) -> None:
        T = make_target("v", str | float, default=0.0)
        assert confarg.load(T, args=["--v", "0.1"], env={}).v == pytest.approx(0.1)

    def test_str_float_negative_decimal(self) -> None:
        T = make_target("v", str | float, default=0.0)
        assert confarg.load(T, args=["--v", "-0.1"], env={}).v == pytest.approx(-0.1)

    def test_str_float_positive_decimal(self) -> None:
        T = make_target("v", str | float, default=0.0)
        assert confarg.load(T, args=["--v", "+0.1"], env={}).v == pytest.approx(0.1)

    def test_int_str_positive(self) -> None:
        T = make_target("v", int | str, default="")
        assert confarg.load(T, args=["--v", "+1"], env={}).v == 1

    def test_int_str_negative(self) -> None:
        T = make_target("v", int | str, default="")
        assert confarg.load(T, args=["--v", "-1"], env={}).v == -1

    def test_str_float_scientific(self) -> None:
        T = make_target("v", str | float, default=0.0)
        assert confarg.load(T, args=["--v", "1e-1"], env={}).v == pytest.approx(0.1)

    def test_plain_str_none_stays_string(self) -> None:
        """Plain str field (not Optional): 'none' is just the string 'none'."""
        T = make_target("v", str, default="")
        assert confarg.load(T, args=["--v", "none"], env={}).v == "none"

    def test_str_fallback_for_unrecognized(self) -> None:
        """In str | float, a non-numeric string falls back to str."""
        T = make_target("v", str | float, default=0.0)
        assert confarg.load(T, args=["--v", "hello"], env={}).v == "hello"


# ---------------------------------------------------------------------------
# .str escape sentinel
# ---------------------------------------------------------------------------


class TestCliStrSentinel:
    """--field.str VALUE forces VALUE as a plain string, bypassing the steal rule."""

    def test_str_escape_none_in_optional_str(self) -> None:
        """--value.str none → string 'none', not Python None."""
        T = make_target("value", str | None, default=None)
        result = confarg.load(T, args=["--value.str", "none"], env={})
        assert result.value == "none"

    def test_str_escape_null_in_optional_str(self) -> None:
        T = make_target("value", str | None, default=None)
        result = confarg.load(T, args=["--value.str", "null"], env={})
        assert result.value == "null"

    def test_str_escape_true_in_str_bool(self) -> None:
        """--value.str true → string 'true', not bool True."""
        T = make_target("value", str | bool, default=False)
        result = confarg.load(T, args=["--value.str", "true"], env={})
        assert result.value == "true"

    def test_str_escape_nan_in_str_float(self) -> None:
        """--value.str nan → string 'nan', not float NaN."""
        T = make_target("value", str | float, default=0.0)
        result = confarg.load(T, args=["--value.str", "nan"], env={})
        assert result.value == "nan"

    def test_str_escape_inf_in_str_float(self) -> None:
        """--value.str inf → string 'inf', not float infinity."""
        T = make_target("value", str | float, default=0.0)
        result = confarg.load(T, args=["--value.str", "inf"], env={})
        assert result.value == "inf"

    def test_str_escape_missing_value_raises(self) -> None:
        T = make_target("value", str | None, default=None)
        with pytest.raises(confarg.ConfargError, match="Missing value"):
            confarg.load(T, args=["--value.str"], env={})


# ---------------------------------------------------------------------------
# JSON composite arguments
# ---------------------------------------------------------------------------


class TestCliJsonComposite:
    """JSON strings as values for composite (non-leaf) CLI arguments."""

    def test_nested_dataclass_as_json(self) -> None:
        """--db '{"host":...}' constructs the nested dataclass."""
        result = confarg.load(
            AppConfig,
            args=["--db", '{"host":"h","port":1,"name":"n"}'],
            env={},
        )
        assert result.db == DbConfig(host="h", port=1, name="n")

    def test_deep_nesting_as_json(self) -> None:
        """JSON spanning multiple levels of nesting."""
        result = confarg.load(
            DeepNested,
            args=["--app", '{"db":{"host":"h","port":1,"name":"n"},"cache":{"enabled":true,"ttl":60}}'],
            env={},
        )
        assert result.app.db.host == "h"
        assert result.app.db.port == 1
        assert result.app.cache.ttl == 60

    def test_optional_nested_dataclass_as_json(self) -> None:
        """JSON for an Optional[Dataclass] field."""
        result = confarg.load(
            WithOptionalNested,
            args=["--db", '{"host":"h","port":5432,"name":"mydb"}'],
            env={},
        )
        assert result.db is not None
        assert result.db.host == "h"
        assert result.db.port == 5432

    def test_dict_field_as_json(self) -> None:
        """--metadata '{...}' constructs the dict field."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        result = confarg.load(
            WithDict,
            args=["--metadata", '{"k1":1,"k2":2}'],
            env={},
        )
        assert result.metadata == {"k1": 1, "k2": 2}

    def test_json_mixed_with_flat_args(self) -> None:
        """JSON sets the bulk of a nested dataclass; a subsequent flat arg overrides one field."""
        result = confarg.load(
            AppConfig,
            args=["--db", '{"host":"h","port":1,"name":"n"}', "--db.port", "5432"],
            env={},
        )
        assert result.db.host == "h"
        assert result.db.port == 5432
        assert result.db.name == "n"

    def test_invalid_json_raises_error(self) -> None:
        """A malformed JSON value raises ConfargError."""
        with pytest.raises(confarg.ConfargError, match="Invalid JSON"):
            confarg.load(
                AppConfig,
                args=["--db", "{not valid json}"],
                env={},
            )


# ---------------------------------------------------------------------------
# List append syntax (--field+)
# ---------------------------------------------------------------------------


class TestCliListAppend:
    """Tests for the --field+ append syntax."""

    def test_append_creates_list_without_config(self) -> None:
        """--items+ creates a new list when no config file is present."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, args=["--items+", "3", "4"], env={})
        assert result.items == [3, 4]

    def test_append_single_value(self) -> None:
        """--items+ with a single value creates a one-element list."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, args=["--items+", "7"], env={})
        assert result.items == [7]

    def test_append_no_values_creates_empty_list(self) -> None:
        """--items+ with no trailing values creates an empty list."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, args=["--items+"], env={})
        assert result.items == []

    def test_append_json_array(self) -> None:
        """--items+ '[1,2]' accepts a JSON array."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, args=["--items+", "[1,2,3]"], env={})
        assert result.items == [1, 2, 3]

    def test_append_string_elements(self) -> None:
        """--tags+ appends string elements."""
        WithList = make_target("tags", list[str], default_factory=list)
        result = confarg.load(WithList, args=["--tags+", "a", "b", "c"], env={})
        assert result.tags == ["a", "b", "c"]

    def test_append_on_non_list_field_raises(self) -> None:
        """+ syntax on a non-list field raises ConfargError."""
        WithInt = make_target("count", int, default=0)
        with pytest.raises(confarg.ConfargError, match=r"\+.*append"):
            confarg.load(WithInt, args=["--count+", "1"], env={})

    def test_index_replacement_still_works(self) -> None:
        """--items.N still works for replacing an element within the existing list."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, args=["--items.0", "10", "--items.1", "20"], env={})
        assert result.items == [10, 20]

    def test_index_out_of_range_with_config_raises(self, tmp_path) -> None:
        """--items.N with N >= len(config_list) raises ConfargError."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("items = [1, 2, 3]\n")
        WithList = make_target("items", list[int], default_factory=list)
        with pytest.raises(confarg.ConfargError, match="extend"):
            confarg.load(WithList, args=["--items.5", "99"], env={}, files=[cfg])

    def test_dotted_field_append(self) -> None:
        """--parent.items+ appends to a nested list field."""
        from dataclasses import dataclass

        @dataclass
        class Parent:
            values: list[int] = field(default_factory=list)

        result = confarg.load(Parent, args=["--values+", "10", "20"], env={})
        assert result.values == [10, 20]

    def test_bracket_string_treated_as_literal_not_json(self) -> None:
        """A value starting with '[' that is not valid JSON is treated as a plain string."""
        WithList = make_target("tags", list[str], default_factory=list)
        result = confarg.load(WithList, args=["--tags", "["], env={})
        assert result.tags == ["["]

    def test_bracket_string_in_append_mode_treated_as_literal(self) -> None:
        """In append mode, a value starting with '[' that is not valid JSON is treated as a string."""
        WithList = make_target("tags", list[str], default_factory=list)
        result = confarg.load(WithList, args=["--tags+", "[", "a"], env={})
        assert result.tags == ["[", "a"]

    def test_brace_string_in_append_mode_treated_as_literal(self) -> None:
        """In append mode, a value starting with '{' that is not valid JSON is treated as a string."""
        WithList = make_target("tags", list[str], default_factory=list)
        result = confarg.load(WithList, args=["--tags+", "{not json"], env={})
        assert result.tags == ["{not json"]


# ---------------------------------------------------------------------------
# Config-file append syntax (--config.field+)
# ---------------------------------------------------------------------------


class TestConfigFileAppend:
    """Tests for the --config.field+ syntax that appends file contents to a list."""

    def test_single_dict_element_appended(self, tmp_yaml) -> None:
        """File with a single dict is appended as one element."""
        base = tmp_yaml("servers:\n  - host: a\n    port: 1\n    name: db1\n")
        extra = tmp_yaml("host: b\nport: 2\nname: db2\n", "extra.yaml")
        result = confarg.load(
            WithNestedList,
            args=["--config", str(base), "--config.servers+", str(extra)],
            env={},
        )
        assert len(result.servers) == 2
        assert result.servers[0].host == "a"
        assert result.servers[1].host == "b"
        assert result.servers[1].port == 2

    def test_wrapped_multi_element_appended(self, tmp_yaml) -> None:
        """File with a single key matching the field name and list value appends all items."""
        base = tmp_yaml("servers:\n  - host: a\n    port: 1\n    name: db1\n")
        extra = tmp_yaml(
            "servers:\n  - host: b\n    port: 2\n    name: db2\n  - host: c\n    port: 3\n    name: db3\n",
            "extra.yaml",
        )
        result = confarg.load(
            WithNestedList,
            args=["--config", str(base), "--config.servers+", str(extra)],
            env={},
        )
        assert len(result.servers) == 3
        assert result.servers[1].host == "b"
        assert result.servers[2].host == "c"

    def test_yaml_list_is_single_list_element(self, tmp_yaml) -> None:
        """File whose root is a YAML list is appended as one element (for list[list[...]])."""
        WithListOfLists = make_target("matrix", list[list[int]], default_factory=list)
        base = tmp_yaml("matrix:\n  - [1, 2]\n  - [3, 4]\n")
        extra = tmp_yaml("- 5\n- 6\n", "extra.yaml")
        result = confarg.load(
            WithListOfLists,
            args=["--config", str(base), "--config.matrix+", str(extra)],
            env={},
        )
        assert result.matrix == [[1, 2], [3, 4], [5, 6]]

    def test_append_without_base_config(self, tmp_yaml) -> None:
        """--config.field+ creates the list when no base config provides one."""
        extra = tmp_yaml("host: a\nport: 1\nname: db1\n", "extra.yaml")
        result = confarg.load(
            WithNestedList,
            args=["--config.servers+", str(extra)],
            env={},
        )
        assert len(result.servers) == 1
        assert result.servers[0].host == "a"

    def test_multiple_append_files_concatenated(self, tmp_yaml) -> None:
        """Multiple --config.field+ files concatenate their items."""
        f1 = tmp_yaml("host: a\nport: 1\nname: db1\n", "f1.yaml")
        f2 = tmp_yaml("host: b\nport: 2\nname: db2\n", "f2.yaml")
        result = confarg.load(
            WithNestedList,
            args=["--config.servers+", str(f1), "--config.servers+", str(f2)],
            env={},
        )
        assert len(result.servers) == 2
        assert result.servers[0].host == "a"
        assert result.servers[1].host == "b"

    def test_multiple_files_same_flag_space_separated(self, tmp_yaml) -> None:
        """Two paths after a single --config.field+ flag are both appended."""
        f1 = tmp_yaml("host: a\nport: 1\nname: db1\n", "f1.yaml")
        f2 = tmp_yaml("host: b\nport: 2\nname: db2\n", "f2.yaml")
        result = confarg.load(
            WithNestedList,
            args=["--config.servers+", str(f1), str(f2)],
            env={},
        )
        assert len(result.servers) == 2
        assert result.servers[0].host == "a"
        assert result.servers[1].host == "b"

    def test_append_then_cli_append(self, tmp_yaml) -> None:
        """Config-file append and CLI --field+ are both applied."""
        base = tmp_yaml("servers:\n  - host: a\n    port: 1\n    name: db1\n")
        extra = tmp_yaml("host: b\nport: 2\nname: db2\n", "extra.yaml")
        result = confarg.load(
            WithNestedList,
            args=[
                "--config",
                str(base),
                "--config.servers+",
                str(extra),
                "--servers+",
                '{"host":"c","port":3,"name":"db3"}',
            ],
            env={},
        )
        assert len(result.servers) == 3
        assert result.servers[0].host == "a"
        assert result.servers[1].host == "b"
        assert result.servers[2].host == "c"

    def test_scalar_list_append_from_file(self, tmp_yaml) -> None:
        """Appending scalars: file wrapped under field name."""
        WithTags = make_target("tags", list[str], default_factory=list)
        base = tmp_yaml("tags:\n  - alpha\n  - beta\n")
        extra = tmp_yaml("tags:\n  - gamma\n  - delta\n", "extra.yaml")
        result = confarg.load(
            WithTags,
            args=["--config", str(base), "--config.tags+", str(extra)],
            env={},
        )
        assert result.tags == ["alpha", "beta", "gamma", "delta"]

    def test_json_append_file(self, tmp_json) -> None:
        """JSON append files work the same way as YAML."""
        import json

        base = tmp_json(json.dumps({"servers": [{"host": "a", "port": 1, "name": "db1"}]}))
        extra = tmp_json(json.dumps({"host": "b", "port": 2, "name": "db2"}), "extra.json")
        result = confarg.load(
            WithNestedList,
            args=["--config", str(base), "--config.servers+", str(extra)],
            env={},
        )
        assert len(result.servers) == 2
        assert result.servers[1].host == "b"

    def test_append_without_subpath_raises(self, tmp_yaml) -> None:
        """--config+ without a field path raises ConfargError."""
        # --config+ is not currently recognized by _parse_cli (doesn't start with "config.")
        # so it raises UnknownArgumentError rather than the config-specific error.
        extra = tmp_yaml("host: a\nport: 1\nname: db1\n", "extra.yaml")
        with pytest.raises((confarg.ConfargError, confarg.UnknownArgumentError)):
            confarg.load(WithNestedList, args=["--config+", str(extra)], env={})


# ---------------------------------------------------------------------------
# config_flag vs field name conflict
# ---------------------------------------------------------------------------


class TestConfigFlagFieldConflict:
    """ConfargError is raised when config_flag shadows a field name."""

    def test_default_config_flag_conflicts_with_field(self) -> None:
        """A field named 'config' conflicts with the default config_flag."""

        @dataclass
        class HasConfigField:
            config: str = ""
            name: str = "x"

        with pytest.raises(confarg.ConfargError, match="config_flag|reserved|config"):
            confarg.load(HasConfigField, args=[], env={})

    def test_custom_config_flag_conflicts_with_field(self) -> None:
        """A custom config_flag that matches a field name raises ConfargError."""

        @dataclass
        class HasConfField:
            conf: str = ""

        with pytest.raises(confarg.ConfargError, match="conf"):
            confarg.load(HasConfField, args=[], env={}, config_flag="conf")

    def test_no_conflict_when_field_name_differs(self) -> None:
        """No error when config_flag does not match any field name."""

        @dataclass
        class NoConflict:
            name: str = "ok"

        result = confarg.load(NoConflict, args=[], env={})
        assert result.name == "ok"

    def test_custom_config_flag_avoids_conflict(self) -> None:
        """Renaming config_flag resolves the conflict with a 'config' field."""

        @dataclass
        class HasConfigField:
            config: str = "default"

        result = confarg.load(HasConfigField, args=["--config", "myvalue"], env={}, config_flag="conf")
        assert result.config == "myvalue"

    def test_conflict_in_union_root_target(self) -> None:
        """Conflict is detected when target is a union and a variant has a field matching config_flag."""

        @dataclass
        class VariantA:
            config: str = ""
            x: int = 0

        @dataclass
        class VariantB:
            name: str = ""

        with pytest.raises(confarg.ConfargError, match="config"):
            confarg.load(VariantA | VariantB, args=[], env={})


# ---------------------------------------------------------------------------
# Deletion syntax: --field- and --list.N-
# ---------------------------------------------------------------------------


class TestCliDelete:
    """Tests for the --field- (dict-key deletion) and --list.N- (list-index deletion) syntax."""

    def test_delete_required_field_raises(self, tmp_toml) -> None:
        """--field- on a required field (no default) causes MissingFieldError."""
        path = tmp_toml("name = 'from_config'\ncount = 5\nrate = 1.0\nverbose = false\n")
        with pytest.raises(confarg.MissingFieldError):
            confarg.load(Flat, args=["--name-"], env={}, files=[path])

    def test_delete_field_resets_to_default(self, tmp_toml) -> None:
        """--field- on a field with a default value causes the default to be used."""
        path = tmp_toml("name = 'cfg_name'\n")
        result = confarg.load(
            WithDefaults,
            args=["--name-"],
            env={},
            files=[path],
        )
        assert result.name == "default"

    def test_delete_nested_field(self, tmp_toml) -> None:
        """--parent.field- removes a nested field; raises MissingFieldError if required."""
        path = tmp_toml("[db]\nhost = 'myhost'\nport = 5432\nname = 'mydb'\n")
        with pytest.raises(confarg.MissingFieldError):
            confarg.load(AppConfig, args=["--db.host-"], env={}, files=[path])

    def test_delete_list_index(self, tmp_toml) -> None:
        """--list.1- removes element at original index 1."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        result = confarg.load(WithList, args=["--items.1-"], env={}, files=[path])
        assert result.items == ["a", "c"]

    def test_delete_first_and_last(self, tmp_toml) -> None:
        """Deleting first and last elements leaves only the middle ones."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c", "d"]\n')
        result = confarg.load(WithList, args=["--items.0-", "--items.3-"], env={}, files=[path])
        assert result.items == ["b", "c"]

    def test_delete_indices_use_original_positions(self, tmp_toml) -> None:
        """--items.1- --items.2- removes original indices 1 and 2, not 1 then (new) 2."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c", "d"]\n')
        result = confarg.load(WithList, args=["--items.1-", "--items.2-"], env={}, files=[path])
        assert result.items == ["a", "d"]

    def test_delete_duplicate_index_raises(self, tmp_toml) -> None:
        """--items.1- --items.1- raises ConfargError (duplicate deletion index)."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        with pytest.raises(confarg.ConfargError, match="[Dd]uplicate"):
            confarg.load(WithList, args=["--items.1-", "--items.1-"], env={}, files=[path])

    def test_delete_out_of_range_raises(self, tmp_toml) -> None:
        """--items.5- on a 3-element list raises ConfargError."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        with pytest.raises(confarg.ConfargError):
            confarg.load(WithList, args=["--items.5-"], env={}, files=[path])

    def test_delete_unknown_field_raises(self) -> None:
        """--nonexistent- raises UnknownArgumentError."""
        result_type = make_target("name", str, default="x")
        with pytest.raises(confarg.UnknownArgumentError):
            confarg.load(result_type, args=["--nonexistent-"], env={})

    def test_delete_then_append(self, tmp_toml) -> None:
        """Deleting an index and appending a value in the same CLI invocation works."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        result = confarg.load(WithList, args=["--items.1-", "--items+", "d"], env={}, files=[path])
        assert result.items == ["a", "c", "d"]

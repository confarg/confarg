# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests: every CLI integration must behave exactly like ``confarg.load()``.

All tests here run against the parametrised ``loader`` fixture (vanilla,
argparse, click, cyclopts) or one of its subsets.  Behavior shared by the
integrations belongs here, written once; only genuinely framework-specific
behavior (help text, registration idioms, completion) stays in the per-backend
test directories.

List-field CLI syntax intentionally differs between integrations and stays
visible: ``TestListSpaceSeparated`` runs on vanilla/argparse/cyclopts and
``TestListRepeatedFlags`` on click/cyclopts.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import (
    Callable,  # noqa: TC003  # used in a runtime dataclass annotation confarg resolves via get_type_hints
)
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pytest

import confarg
from confarg.cli.argparse._build import build_static_flags
from confarg.exceptions import ConfargError, MissingFieldError, TypeCoercionError
from tests.conftest import AppConfig, CacheConfig, DbConfig, make_target

if TYPE_CHECKING:
    from tests._loaders import ConfargLoader

# ---------------------------------------------------------------------------
# Shared dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Simple:
    """Simple flat dataclass with defaults."""

    host: str = "localhost"
    port: int = 8080


@dataclass
class Nested:
    """Dataclass with a nested struct field."""

    db: Simple = dataclasses.field(default_factory=Simple)
    debug: bool = False


@dataclass
class WithCsvRows:
    """Dataclass whose list field is populated from a CSV include."""

    db: list[Simple] = dataclasses.field(default_factory=list)


@dataclass
class WithList:
    """Dataclass with a list field."""

    tags: list[str] = dataclasses.field(default_factory=list)


@dataclass
class WithOptional:
    """Dataclass with an optional field."""

    name: str = "default"
    label: str | None = None


class Color(Enum):
    """Color enumeration for enum tests."""

    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@dataclass
class WithEnum:
    """Dataclass with an Enum field."""

    color: Color = Color.RED


@dataclass
class WithLiteral:
    """Dataclass with a Literal field."""

    level: Literal["debug", "info", "warning"] = "info"


@dataclass
class _WithStrFloat:
    input: str | float


@dataclass
class _WithStrBool:
    input: str | bool


class _StealMarker:
    """Module-level class used as a dotted-path target for str | type stealing tests."""


@dataclass
class _WithStrType:
    value: str | type


@dataclass
class _WithStrTuple:
    input: str | tuple[str, str]


@dataclass
class _WithStrList:
    input: str | list[str]


@dataclass
class _WithBoolList:
    input: bool | list[str]


@dataclass
class _WithStrBoolList:
    values: list[str | bool] = dataclasses.field(default_factory=list)


@dataclass
class _WithIntNoneList:
    values: list[int | None] = dataclasses.field(default_factory=list)


@dataclass
class _BaseDB:
    """Abstract base database config (inheritance dispatch)."""


@dataclass
class _SQLiteDB(_BaseDB):
    dbpath: str


@dataclass
class _ServerDB(_BaseDB):
    host: str
    port: int


@dataclass
class _RootSQLite:
    """SQLite config for union-root tests."""

    dbpath: str


@dataclass
class _RootDBServer:
    """DB server config for union-root tests."""

    host: str
    port: int
    name: str


_RootDBConfig: Any = _RootSQLite | _RootDBServer


@dataclass
class _RootMariaDBTyped:
    """MariaDB variant with a Literal discriminator."""

    type: Literal["mariadb"] = "mariadb"
    host: str = ""


@dataclass
class _RootPostgreTyped:
    """PostgreSQL variant with a Literal discriminator."""

    type: Literal["postgres"] = "postgres"
    host: str = ""


_RootTypedDBConfig: Any = _RootMariaDBTyped | _RootPostgreTyped


@dataclass
class _WithAnyField:
    """A field the two-gate JSON magic can't reach — only ``.json`` decodes it."""

    data: Any = None


@dataclass
class _WithJsonNamedField:
    """A field literally named ``json`` (a cast word): the real field must win."""

    json: int = 0


@dataclass
class _InnerJson:
    json: int = 0


@dataclass
class _OuterInner:
    inner: _InnerJson = dataclasses.field(default_factory=_InnerJson)


@dataclass
class _WithDictField:
    d: dict[str, int] = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loading basics
# ---------------------------------------------------------------------------


class TestLoadContract:
    """Core load behavior every integration must share."""

    def test_scalar_values(self, loader: ConfargLoader) -> None:
        """CLI values are coerced to the field types."""
        cfg = loader.load(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        assert cfg.host == "myhost"
        assert cfg.port == 9090

    def test_defaults_used_when_not_provided(self, loader: ConfargLoader) -> None:
        """Omitted options fall back to dataclass defaults."""
        cfg = loader.load(Simple, argv=[], env={})
        assert cfg.host == "localhost"
        assert cfg.port == 8080

    def test_only_cli_values_override_defaults(self, loader: ConfargLoader) -> None:
        """Provided options override defaults; omitted ones keep them."""
        cfg = loader.load(Simple, argv=["--host", "explicit"], env={})
        assert cfg.host == "explicit"
        assert cfg.port == 8080

    def test_nested(self, loader: ConfargLoader) -> None:
        """Dotted options are nested into the correct sub-struct."""
        cfg = loader.load(Nested, argv=["--db.host", "db1", "--debug", "true"], env={})
        assert cfg.db.host == "db1"
        assert cfg.debug is True

    def test_missing_required_raises(self, loader: ConfargLoader) -> None:
        """A required field absent from all sources raises MissingFieldError."""
        with pytest.raises(MissingFieldError):
            loader.load(DbConfig, argv=[], env={})

    def test_optional_field_absent(self, loader: ConfargLoader) -> None:
        """Optional fields default to None when absent."""
        cfg = loader.load(WithOptional, argv=[], env={})
        assert cfg.name == "default"
        assert cfg.label is None

    def test_optional_field_provided(self, loader: ConfargLoader) -> None:
        """Optional fields are set when provided."""
        cfg = loader.load(WithOptional, argv=["--label", "hello"], env={})
        assert cfg.label == "hello"

    def test_enum_by_value(self, loader: ConfargLoader) -> None:
        """Enum fields accept enum values (not just names)."""
        cfg = loader.load(WithEnum, argv=["--color", "blue"], env={})
        assert cfg.color is Color.BLUE

    def test_literal_field(self, loader: ConfargLoader) -> None:
        """Literal fields accept their member values."""
        cfg = loader.load(WithLiteral, argv=["--level", "warning"], env={})
        assert cfg.level == "warning"

    def test_env_vars(self, loader: ConfargLoader) -> None:
        """Environment variables are merged at lower priority than CLI."""
        cfg = loader.load(
            Simple,
            argv=[],
            env={"MYAPP_HOST": "envhost", "MYAPP_PORT": "1234"},
            env_prefix="MYAPP_",
        )
        assert cfg.host == "envhost"
        assert cfg.port == 1234

    def test_cli_overrides_env(self, loader: ConfargLoader) -> None:
        """CLI values have higher priority than env vars."""
        cfg = loader.load(
            Simple,
            argv=["--host", "clihost"],
            env={"MYAPP_HOST": "envhost"},
            env_prefix="MYAPP_",
        )
        assert cfg.host == "clihost"

    def test_env_disabled_by_default(self, loader: ConfargLoader) -> None:
        """Env vars are ignored when env_prefix is None (the default)."""
        cfg = loader.load(Simple, argv=[], env={"HOST": "envhost", "PORT": "9999"})
        assert cfg.host == "localhost"
        assert cfg.port == 8080


# ---------------------------------------------------------------------------
# List syntax — intentionally split per convention
# ---------------------------------------------------------------------------


class TestListSpaceSeparated:
    """Space-separated list values (vanilla, argparse, cyclopts)."""

    def test_list_field(self, space_sep_loader: ConfargLoader) -> None:
        """--tags a b c collects into a list."""
        cfg = space_sep_loader.load(WithList, argv=["--tags", "a", "b", "c"], env={})
        assert cfg.tags == ["a", "b", "c"]


class TestListRepeatedFlags:
    """Repeated-flag list values (click, cyclopts)."""

    def test_list_field(self, repeated_loader: ConfargLoader) -> None:
        """--tags a --tags b collects into a list."""
        cfg = repeated_loader.load(WithList, argv=["--tags", "x", "--tags", "y"], env={})
        assert cfg.tags == ["x", "y"]


# ---------------------------------------------------------------------------
# Bool convention
# ---------------------------------------------------------------------------


class TestBoolValueConvention:
    """The explicit --flag true/false convention holds in every integration."""

    def test_bool_explicit_true(self, loader: ConfargLoader) -> None:
        """--debug true sets a bool field to True."""
        assert loader.load(Nested, argv=["--debug", "true"], env={}).debug is True

    def test_bool_explicit_false(self, loader: ConfargLoader) -> None:
        """--debug false sets a bool field to False."""
        assert loader.load(Nested, argv=["--debug", "false"], env={}).debug is False

    def test_no_negative_flag_registered(self, populating_loader: ConfargLoader) -> None:
        """No --no-debug style negative flag is generated for bool fields."""
        flags = populating_loader.registered_flags(Nested, config_flag="")
        assert flags is not None
        assert "no-debug" not in flags
        assert "no_debug" not in flags


# ---------------------------------------------------------------------------
# Union stealing rule and cast overrides
# ---------------------------------------------------------------------------


class TestStealingContract:
    """Scalar-union stealing rule and .str/.int cast overrides."""

    def test_str_float_stealing(self, loader: ConfargLoader) -> None:
        """--input inf coerces to float for str | float (stealing rule)."""
        cfg = loader.load(_WithStrFloat, argv=["--input", "inf"], env={})
        assert math.isinf(cfg.input)
        assert type(cfg.input) is float

    def test_str_bool_stealing(self, loader: ConfargLoader) -> None:
        """--input yes coerces to True for str | bool (stealing rule)."""
        cfg = loader.load(_WithStrBool, argv=["--input", "yes"], env={})
        assert cfg.input is True

    def test_str_override(self, loader: ConfargLoader) -> None:
        """--input.str yes preserves 'yes' as str, bypassing bool stealing."""
        cfg = loader.load(_WithStrBool, argv=["--input.str", "yes"], env={})
        assert cfg.input == "yes"
        assert type(cfg.input) is str

    def test_str_type_stealing_builtin(self, loader: ConfargLoader) -> None:
        """--value int resolves to the int class for str | type (type steals over str)."""
        cfg = loader.load(_WithStrType, argv=["--value", "int"], env={})
        assert cfg.value is int

    def test_str_type_stealing_dotted_path(self, loader: ConfargLoader) -> None:
        """--value <dotted> resolves to the class for str | type (type steals over str)."""
        path = f"{_StealMarker.__module__}.{_StealMarker.__qualname__}"
        cfg = loader.load(_WithStrType, argv=["--value", path], env={})
        assert cfg.value is _StealMarker

    def test_str_type_override(self, loader: ConfargLoader) -> None:
        """--value.str int preserves 'int' as a string, bypassing type stealing."""
        cfg = loader.load(_WithStrType, argv=["--value.str", "int"], env={})
        assert cfg.value == "int"
        assert type(cfg.value) is str


# ---------------------------------------------------------------------------
# Union with a sequence variant (str | tuple[...], str | list[str])
# ---------------------------------------------------------------------------


class TestUnionWithSequenceContract:
    """A union mixing a scalar with a sequence variant accepts one or many tokens.

    One token stays a bare scalar; two-or-more tokens form the sequence. The
    multi-token CLI syntax follows the established per-convention split, so those
    cases use the space_sep / repeated fixtures.
    """

    def test_str_tuple_single_value_is_scalar(self, loader: ConfargLoader) -> None:
        """--input foo yields the bare str for str | tuple[str, str]."""
        cfg = loader.load(_WithStrTuple, argv=["--input", "foo"], env={})
        assert cfg.input == "foo"

    def test_str_list_single_value_is_scalar(self, loader: ConfargLoader) -> None:
        """--input foo yields the bare str for str | list[str]."""
        cfg = loader.load(_WithStrList, argv=["--input", "foo"], env={})
        assert cfg.input == "foo"

    def test_bool_list_single_value_matches_scalar(self, loader: ConfargLoader) -> None:
        """--input true matches the bool variant for bool | list[str] (scalar priority)."""
        cfg = loader.load(_WithBoolList, argv=["--input", "true"], env={})
        assert cfg.input is True

    def test_bool_list_single_value_falls_back_to_list(self, loader: ConfargLoader) -> None:
        """--input hello: bool rejects it, so it fills list[str] as ['hello'] (the reported bug)."""
        cfg = loader.load(_WithBoolList, argv=["--input", "hello"], env={})
        assert cfg.input == ["hello"]

    def test_str_tuple_two_values_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """--input foo bar builds the tuple (vanilla, argparse, cyclopts)."""
        cfg = space_sep_loader.load(_WithStrTuple, argv=["--input", "foo", "bar"], env={})
        assert cfg.input == ("foo", "bar")

    def test_str_tuple_two_values_repeated(self, repeated_loader: ConfargLoader) -> None:
        """--input foo --input bar builds the tuple (click, cyclopts)."""
        cfg = repeated_loader.load(_WithStrTuple, argv=["--input", "foo", "--input", "bar"], env={})
        assert cfg.input == ("foo", "bar")

    def test_str_list_two_values_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """--input foo bar builds the list (vanilla, argparse, cyclopts)."""
        cfg = space_sep_loader.load(_WithStrList, argv=["--input", "foo", "bar"], env={})
        assert cfg.input == ["foo", "bar"]

    def test_str_list_two_values_repeated(self, repeated_loader: ConfargLoader) -> None:
        """--input foo --input bar builds the list (click, cyclopts)."""
        cfg = repeated_loader.load(_WithStrList, argv=["--input", "foo", "--input", "bar"], env={})
        assert cfg.input == ["foo", "bar"]

    def test_str_list_empty_builds_empty_list_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """--input with no token builds [] for str | list[str] (vanilla, argparse, cyclopts)."""
        cfg = space_sep_loader.load(_WithStrList, argv=["--input"], env={})
        assert cfg.input == []

    def test_str_tuple_empty_raises_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """--input with no token is rejected for str | tuple[str, str] (no varlen variant)."""
        with pytest.raises(ConfargError):
            space_sep_loader.load(_WithStrTuple, argv=["--input"], env={})

    def test_flag_registered(self, populating_loader: ConfargLoader) -> None:
        """The union-with-sequence field flag is registered on every adapter."""
        for target in (_WithStrTuple, _WithStrList):
            flags = populating_loader.registered_flags(target)
            assert flags is not None
            assert "input" in flags


# ---------------------------------------------------------------------------
# Inline JSON array as a single token (nargs="*" collection / union-seq fields)
# ---------------------------------------------------------------------------


class TestJsonArrayTokenContract:
    """A single inline JSON-array token sets a collection field, matching confarg.load().

    A ``nargs="*"`` flag (a varlen list or a union-with-sequence-variant) accepts one
    inline JSON array as its whole value. Elements keep their JSON types: unlike the
    space-separated form, strings are exempt from the stealing rule and ``null`` is
    expressible. Every adapter must agree with the vanilla loader.
    """

    def test_varlen_list_json_array(self, loader: ConfargLoader) -> None:
        """--values '["hello", "yes", "well"]' -> strings; "yes" is NOT stolen to True."""
        cfg = loader.load(_WithStrBoolList, argv=["--values", '["hello", "yes", "well"]'], env={})
        assert cfg.values == ["hello", "yes", "well"]

    def test_varlen_list_json_preserves_null(self, loader: ConfargLoader) -> None:
        """--values '[null, 550]' -> [None, 550]; null cannot be expressed space-separated."""
        cfg = loader.load(_WithIntNoneList, argv=["--values", "[null, 550]"], env={})
        assert cfg.values == [None, 550]

    def test_union_seq_json_array(self, loader: ConfargLoader) -> None:
        """--input '["a", "b"]' fills the list variant of str | list[str]."""
        cfg = loader.load(_WithStrList, argv=["--input", '["a", "b"]'], env={})
        assert cfg.input == ["a", "b"]

    def test_invalid_json_falls_back_to_literal(self, loader: ConfargLoader) -> None:
        """A non-JSON '[' token is not parsed; it stays a single literal element."""
        cfg = loader.load(_WithStrBoolList, argv=["--values", "[oops"], env={})
        assert cfg.values == ["[oops"]

    def test_merged_dict_matches_vanilla(self, loader: ConfargLoader) -> None:
        """The raw merged dict is byte-identical across all four loaders (plain values)."""
        merged = loader.merge(_WithStrBoolList, argv=["--values", '["hello", "yes", "well"]'], env={})
        assert merged == {"values": ["hello", "yes", "well"]}


# ---------------------------------------------------------------------------
# Config files
# ---------------------------------------------------------------------------


class TestConfigFilesContract:
    """Config-file loading and precedence behave identically in every integration."""

    def test_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Files passed via --config are loaded and merged."""
        cfg_file = tmp_yaml("host: filehost\nport: 5432\n")
        cfg = loader.load(Simple, argv=["--config", str(cfg_file)], env={})
        assert cfg.host == "filehost"
        assert cfg.port == 5432

    def test_config_file_via_files_param(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Files passed via files= are loaded without any CLI flag."""
        cfg_file = tmp_yaml("host: file_host\nport: 9999\n")
        cfg = loader.load(Simple, argv=[], env={}, files=[cfg_file])
        assert cfg.host == "file_host"
        assert cfg.port == 9999

    def test_csv_include_coerces_to_target_types(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        tmp_yaml,
    ) -> None:
        """A CSV pulled in by __include__ coerces its cells to the target leaf types."""
        (tmp_path / "rows.csv").write_text("host,port\nfilehost,5432\n")
        cfg_file = tmp_yaml("db:\n  __include__: ./rows.csv\n")
        cfg = loader.load(WithCsvRows, argv=["--config", str(cfg_file)], env={})
        assert cfg.db == [Simple(host="filehost", port=5432)]

    def test_include_list_layers_in_order(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        tmp_yaml,
    ) -> None:
        """A list-valued __include__ layers left to right, later entries winning."""
        (tmp_path / "a.yaml").write_text("host: a_host\nport: 1\n")
        (tmp_path / "b.yaml").write_text("host: b_host\n")
        cfg_file = tmp_yaml("__include__: [./a.yaml, ./b.yaml]\n")
        cfg = loader.load(Simple, argv=["--config", str(cfg_file)], env={})
        assert cfg == Simple(host="b_host", port=1)

    def test_cli_overrides_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """CLI values take priority over config-file values."""
        cfg_file = tmp_yaml("host: filehost\nport: 1111\n")
        cfg = loader.load(Simple, argv=["--config", str(cfg_file), "--port", "2222"], env={})
        assert cfg.host == "filehost"
        assert cfg.port == 2222

    def test_env_overrides_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Env vars take priority over config-file values."""
        cfg_file = tmp_yaml("host: filehost\nport: 1111\n")
        cfg = loader.load(
            Simple,
            argv=["--config", str(cfg_file)],
            env={"MYAPP_PORT": "3333"},
            env_prefix="MYAPP_",
        )
        assert cfg.host == "filehost"
        assert cfg.port == 3333

    def test_multiple_config_files_merged(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Later --config files override earlier ones (repeated-flag form works everywhere)."""
        base = tmp_yaml("host: base\nport: 1000\n", filename="base.yaml")
        override = tmp_yaml("port: 2000\n", filename="override.yaml")
        cfg = loader.load(Simple, argv=["--config", str(base), "--config", str(override)], env={})
        assert cfg.host == "base"
        assert cfg.port == 2000

    def test_subkey_config_loads_under_subkey(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.db file.yaml loads file contents under the 'db' key."""
        db_cfg = tmp_yaml("host: db_host\nport: 5555\nname: db_name\n", filename="db.yaml")
        cfg = loader.load(AppConfig, argv=["--config.db", str(db_cfg)], env={})
        assert cfg.db == DbConfig(host="db_host", port=5555, name="db_name")

    def test_subkey_and_root_config_combined(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Root --config and --config.db combine; CLI still wins over both."""
        root_cfg = tmp_yaml("debug: true\ncache:\n  enabled: false\n", filename="root.yaml")
        db_cfg = tmp_yaml("host: from_file\nport: 1111\nname: n\n", filename="db.yaml")
        cfg = loader.load(
            AppConfig,
            argv=["--config", str(root_cfg), "--config.db", str(db_cfg), "--db.port", "9999"],
            env={},
        )
        assert cfg.debug is True
        assert cfg.cache == CacheConfig(enabled=False)
        assert cfg.db.host == "from_file"
        assert cfg.db.port == 9999

    def test_left_to_right_subkey_then_root(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.db db.yaml --config root.yaml: root file (rightmost) wins for db."""
        root_cfg = tmp_yaml(
            "db:\n  host: root_host\n  port: 1111\n  name: root_db\ncache:\n  enabled: true\n",
            filename="root.yaml",
        )
        db_cfg = tmp_yaml("host: db_host\nport: 5555\nname: db_db\n", filename="db.yaml")
        cfg = loader.load(AppConfig, argv=["--config.db", str(db_cfg), "--config", str(root_cfg)], env={})
        assert cfg.db == DbConfig(host="root_host", port=1111, name="root_db")

    def test_left_to_right_root_then_subkey(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config root.yaml --config.db db.yaml: subkey file (rightmost) wins for db."""
        root_cfg = tmp_yaml(
            "db:\n  host: root_host\n  port: 1111\n  name: root_db\ncache:\n  enabled: true\n",
            filename="root.yaml",
        )
        db_cfg = tmp_yaml("host: db_host\nport: 5555\nname: db_db\n", filename="db.yaml")
        cfg = loader.load(AppConfig, argv=["--config", str(root_cfg), "--config.db", str(db_cfg)], env={})
        assert cfg.db == DbConfig(host="db_host", port=5555, name="db_db")

    def test_config_flag_registered_by_default(self, populating_loader: ConfargLoader) -> None:
        """populate_* registers the --config flag (and subkey flags) by default."""
        flags = populating_loader.registered_flags(AppConfig)
        assert flags is not None
        assert "config" in flags
        assert "config.db" in flags

    def test_config_flag_absent_when_disabled(self, populating_loader: ConfargLoader) -> None:
        """config_flag='' suppresses --config registration."""
        flags = populating_loader.registered_flags(Simple, config_flag="")
        assert flags is not None
        assert "config" not in flags

    def test_custom_config_flag_name(self, populating_loader: ConfargLoader) -> None:
        """config_flag='cfg' registers --cfg instead of --config."""
        flags = populating_loader.registered_flags(Simple, config_flag="cfg")
        assert flags is not None
        assert "cfg" in flags
        assert "config" not in flags

    def test_config_subkeys_false_root_only(self, populating_loader: ConfargLoader) -> None:
        """config_subkeys=False registers only the root --config flag."""
        flags = populating_loader.registered_flags(AppConfig, config_subkeys=False)
        assert flags is not None
        assert "config" in flags
        assert "config.db" not in flags


# ---------------------------------------------------------------------------
# Pipeline parity — regressions for former vanilla-vs-adapter divergences
# ---------------------------------------------------------------------------


class TestPipelineParity:
    """Regression tests for former vanilla-vs-adapter divergences.

    One test per behavior that historically diverged between confarg.load()
    and the CLI adapters before both shared _merge_sources.
    """

    def test_custom_config_flag_env_pointer(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A custom config_flag is honored for env-specified config files.

        Adapters used to hard-default the env-pointer segment to "config",
        silently ignoring a custom flag name.
        """
        cfg = tmp_yaml("host: envhost\nport: 5432\nname: envdb\n")
        result = loader.load(
            DbConfig,
            argv=[],
            env={"MYAPP_CONF": str(cfg)},
            env_prefix="MYAPP_",
            config_flag="conf",
        )
        assert result == DbConfig(host="envhost", port=5432, name="envdb")

    def test_config_append_syntax(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.field+ appends file items to a list instead of replacing it.

        Adapters used to load all CLI config files with plain replace semantics,
        ignoring the trailing ``+``.
        """
        base = tmp_yaml("users:\n  - alice\n  - bob\n", filename="base.yaml")
        extra = tmp_yaml("users:\n  - carol\n", filename="extra.yaml")
        target = make_target("users", list[str])
        result = loader.load(
            target,
            argv=["--config.users+", str(extra)],
            env={},
            files=[base],
        )
        assert result.users == ["alice", "bob", "carol"]

    def test_env_config_loads_named_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """env_config names an env var whose value is a config file path.

        Adapters used to not support env_config at all.  The env var itself must
        not be parsed as a field (no unknown-field warning / stray value).
        """
        cfg = tmp_yaml("host: filehost\nport: 1234\nname: filedb\n")
        result = loader.load(
            DbConfig,
            argv=[],
            env={"MYAPP_CONFIG_FILE": str(cfg), "MYAPP_PORT": "9999"},
            env_prefix="MYAPP_",
            env_config="MYAPP_CONFIG_FILE",
        )
        # Inline env var wins over the env_config file; other fields come from the file.
        assert result == DbConfig(host="filehost", port=9999, name="filedb")

    def test_env_config_subpath_ordering(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Env-specified config files load shallow-to-deep, so deeper paths win.

        Adapters used to load env config files in mapping order without sorting.
        """
        base = tmp_yaml(
            """\
            db:
              host: basehost
              port: 1111
              name: basedb
            cache:
              enabled: false
            """,
            filename="base.yaml",
        )
        db = tmp_yaml("host: dbhost\nport: 2222\nname: dbdb\n", filename="db.yaml")
        # Mapping order is deliberately deep-first; the pipeline must sort so the
        # global file loads first and the subpath file overrides it.
        result = loader.load(
            AppConfig,
            argv=[],
            env={"MYAPP_CONFIG__DB": str(db), "MYAPP_CONFIG": str(base)},
            env_prefix="MYAPP_",
        )
        assert result.db == DbConfig(host="dbhost", port=2222, name="dbdb")
        assert result.cache == CacheConfig(enabled=False)

    def test_empty_config_flag_treats_config_as_field(self, loader: ConfargLoader) -> None:
        """config_flag="" disables config handling; a field named "config" stays a field."""
        target = make_target("config", str)
        result = loader.load(
            target,
            argv=[],
            env={"MYAPP_CONFIG": "hello"},
            env_prefix="MYAPP_",
            config_flag="",
        )
        assert result.config == "hello"

    def test_scalar_root_target_via_env(self, loader: ConfargLoader) -> None:
        """A non-struct root target works through every integration (build's __root__ path).

        Adapters used to call construct() directly, which lacked the __root__
        unwrapping that build() does for scalar targets.  CLI input for scalar
        roots needs cli_prefix (vanilla-only), so the shared path here is env.
        """
        result = loader.load(int, argv=[], env={"VALUE": "8080"}, env_prefix="", config_flag="")
        assert result == 8080


# ---------------------------------------------------------------------------
# Inheritance-based dispatch (base class with subclasses)
# ---------------------------------------------------------------------------


class TestInheritanceDispatchContract:
    """Base-class targets dispatch to subclasses identically in every integration."""

    def test_class_flag_registered(self, populating_loader: ConfargLoader) -> None:
        """populate_* registers --class for a base dataclass with subclasses."""
        flags = populating_loader.registered_flags(_BaseDB, config_flag="")
        assert flags is not None
        assert "class" in flags

    def test_subclass_fields_registered(self, populating_loader: ConfargLoader) -> None:
        """populate_* also registers subclass fields as top-level flags."""
        flags = populating_loader.registered_flags(_BaseDB, config_flag="")
        assert flags is not None
        assert {"dbpath", "host", "port"} <= flags

    def test_dispatch_sqlite(self, loader: ConfargLoader) -> None:
        """--class selects and constructs the SQLite subclass."""
        result = loader.load(
            _BaseDB,
            argv=["--class", f"{__name__}._SQLiteDB", "--dbpath", "/var/db/app.sqlite"],
            env={},
            config_flag="",
        )
        assert isinstance(result, _SQLiteDB)
        assert result.dbpath == "/var/db/app.sqlite"

    def test_dispatch_server(self, loader: ConfargLoader) -> None:
        """--class selects and constructs the server subclass."""
        result = loader.load(
            _BaseDB,
            argv=["--class", f"{__name__}._ServerDB", "--host", "db.example.com", "--port", "5432"],
            env={},
            config_flag="",
        )
        assert isinstance(result, _ServerDB)
        assert result.host == "db.example.com"
        assert result.port == 5432

    def test_no_class_tag_raises(self, loader: ConfargLoader) -> None:
        """A base class with subclasses but no --class raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="discriminator"):
            loader.load(_BaseDB, argv=["--dbpath", "/var/db/app.sqlite"], env={}, config_flag="")


# ---------------------------------------------------------------------------
# Root-level union target (target IS a union, not a struct containing one)
# ---------------------------------------------------------------------------


class TestUnionRootContract:
    """Union-of-structs root targets work identically in every integration."""

    def test_union_root_flags_built(self) -> None:
        """build_static_flags generates --class and all variant fields for a union root."""
        flags = build_static_flags(_RootDBConfig, union_tag="class", config_flag="")
        names = {f.name for f in flags}
        assert {"class", "dbpath", "host", "port", "name"} <= names

    def test_union_root_flags_registered(self, populating_loader: ConfargLoader) -> None:
        """populate_* registers --class and all variant fields for a union root."""
        flags = populating_loader.registered_flags(_RootDBConfig, config_flag="")
        assert flags is not None
        assert {"class", "dbpath", "host", "port", "name"} <= flags

    def test_union_root_round_trip_sqlite(self, loader: ConfargLoader) -> None:
        """--dbpath alone selects the SQLite variant without needing --class."""
        result = loader.load(_RootDBConfig, argv=["--dbpath", "/tmp/x.db"], env={}, config_flag="")
        assert isinstance(result, _RootSQLite)
        assert result.dbpath == "/tmp/x.db"

    def test_union_root_round_trip_db_server(self, loader: ConfargLoader) -> None:
        """DB server fields alone select the server variant without needing --class."""
        result = loader.load(
            _RootDBConfig,
            argv=["--host", "db.example.com", "--port", "5432", "--name", "mydb"],
            env={},
            config_flag="",
        )
        assert isinstance(result, _RootDBServer)
        assert result.host == "db.example.com"
        assert result.port == 5432
        assert result.name == "mydb"

    def test_union_root_explicit_class_tag(self, loader: ConfargLoader) -> None:
        """--class overrides structural disambiguation for the union root."""
        result = loader.load(
            _RootDBConfig,
            argv=["--class", f"{__name__}._RootSQLite", "--dbpath", "/tmp/x.db"],
            env={},
            config_flag="",
        )
        assert isinstance(result, _RootSQLite)
        assert result.dbpath == "/tmp/x.db"

    def test_union_root_literal_discriminator_choices_merged(self) -> None:
        """A Literal discriminator shared across variants accepts every variant's value.

        Each variant contributes a ``type`` FlagSpec with its own single-member choices;
        these must be merged into one flag rather than first-wins-collapsed.
        """
        flags = build_static_flags(_RootTypedDBConfig, union_tag="class", config_flag="")
        type_specs = [f for f in flags if f.name == "type"]
        assert len(type_specs) == 1
        assert set(type_specs[0].choices or []) == {"mariadb", "postgres"}

    def test_union_root_literal_discriminator_selects_variant(self, loader: ConfargLoader) -> None:
        """--type <value> selects the matching union variant regardless of order."""
        maria = loader.load(_RootTypedDBConfig, argv=["--type", "mariadb", "--host", "h"], env={}, config_flag="")
        assert isinstance(maria, _RootMariaDBTyped)
        postgres = loader.load(_RootTypedDBConfig, argv=["--type", "postgres", "--host", "h"], env={}, config_flag="")
        assert isinstance(postgres, _RootPostgreTyped)


# ---------------------------------------------------------------------------
# merge() — the raw-dict variant
# ---------------------------------------------------------------------------


class TestMergeContract:
    """merge_* returns the raw merged dict, identically in every integration."""

    def test_returns_dict(self, loader: ConfargLoader) -> None:
        """Merge returns a dict, not a dataclass instance."""
        result = loader.merge(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        assert isinstance(result, dict)

    def test_cli_values_in_dict(self, loader: ConfargLoader) -> None:
        """CLI-provided values appear in the returned dict, eagerly coerced.

        Every integration coerces typed leaf values at merge time, so the raw
        dict carries ``port`` as the int ``9090`` regardless of which backend
        produced it (vanilla and adapters agree byte-for-byte).
        """
        result = loader.merge(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        assert result["host"] == "myhost"
        assert result["port"] == 9090

    def test_expressions_preserved(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Expression strings from config files are kept intact (not resolved)."""
        cfg = tmp_yaml("host: myhost\nport: '${host}'\n")
        result = loader.merge(Simple, argv=["--config", str(cfg)], env={})
        assert result["port"] == "${host}"

    def test_round_trip_equivalence(self, loader: ConfargLoader) -> None:
        """build(target, merge(...)) equals load(...) for the same inputs."""
        argv = ["--host", "myhost", "--port", "9090"]
        raw = loader.merge(Simple, argv=argv, env={})
        assert confarg.build(Simple, raw) == loader.load(Simple, argv=argv, env={})

    def test_dump_file_from_raw_dict(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """dump_file accepts the raw dict returned by merge without raising."""
        out = tmp_path / "out.yaml"
        raw = loader.merge(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        confarg.dump_file(raw, out)
        assert out.exists()

    def test_dump_file_round_trip_via_instance(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Round-tripping through a built instance gives back the same config."""
        out = tmp_path / "out.yaml"
        raw = loader.merge(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        confarg.dump_file(confarg.build(Simple, raw), out)
        reloaded = confarg.load(Simple, argv=[], files=[out], env={})
        assert reloaded.host == "myhost"
        assert reloaded.port == 9090


# ---------------------------------------------------------------------------
# Collection patches — list index/append/delete and dict subkeys via CLI
# ---------------------------------------------------------------------------


@dataclass
class _PatchSqlite:
    """List-element struct for collection-patch tests."""

    dbpath: str = ""


@dataclass
class _WithUsers:
    """List-of-str field with a default base."""

    users: list[str] = dataclasses.field(default_factory=list)


@dataclass
class _WithLang:
    """Fixed-length tuple field."""

    lang: tuple[str, str] = ("en", "EN")


@dataclass
class _WithPair:
    """Fixed-length tuple field with no default (built element-by-element from CLI)."""

    input: tuple[int, int]


@dataclass
class _WithTriple:
    """Fixed-length 3-tuple field — completed from a shorter config base via index patch."""

    input: tuple[int, int, int]


@dataclass
class _WithDbs:
    """List-of-struct field."""

    dbs: list[_PatchSqlite] = dataclasses.field(default_factory=list)


@dataclass
class _WithMap:
    """Dict field (skipped at static registration; patched via argv subkeys)."""

    data: dict[str, int] = dataclasses.field(default_factory=dict)


@dataclass
class _WithStrBools:
    """List-of-scalar-union field — elements are subject to the stealing rule."""

    input: list[str | bool] = dataclasses.field(default_factory=list)


@dataclass
class _WithGrid:
    """List-of-list field — element is itself a sequence (nested index patch)."""

    grid: list[list[int]] = dataclasses.field(default_factory=list)


@dataclass
class _WithPairs:
    """List-of-tuple field — element is a fixed-length sequence (nested index patch)."""

    pairs: list[tuple[int, int]] = dataclasses.field(default_factory=list)


class TestCollectionPatchContract:
    """List index/append/delete and dict-subkey CLI patches resolve identically everywhere.

    These were vanilla-only before ``build_dynamic_flags`` registered the
    argv-derived patch flags and ``_parse_cli(..., patch_only=True)`` applied
    them in command order on top of the framework parse result.
    """

    def test_index_set(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field.N value`` replaces a single list element."""
        base = tmp_yaml("users: [alice, bob, claire]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.0", "allan"], env={})
        assert cfg.users == ["allan", "bob", "claire"]

    def test_negative_index_set(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Negative indices count from the end."""
        base = tmp_yaml("users: [alice, bob, claire]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.-1", "billy"], env={})
        assert cfg.users == ["alice", "bob", "billy"]

    def test_nested_index_set(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Indices compose with sub-field paths (``--dbs.1.dbpath``)."""
        base = tmp_yaml("dbs:\n  - dbpath: a\n  - dbpath: b\n")
        cfg = loader.load(_WithDbs, argv=["--config", str(base), "--dbs.1.dbpath", "z"], env={})
        assert cfg.dbs == [_PatchSqlite("a"), _PatchSqlite("z")]

    def test_index_force_cast_bypasses_stealing(self, loader: ConfargLoader) -> None:
        """``--field.N.str`` force-casts a single list element, bypassing the stealing rule.

        The cast path (``input.1``) is itself a collection-patch path, so it is applied by the
        argv-order patch scan, not the flat collector — the whole reason both the patch-flag
        registration and ``_parse_cli(patch_only=True)`` route the decision through
        ``_is_collection_patch_path`` rather than assuming every cast is a plain-field cast.
        """
        cfg = loader.load(
            _WithStrBools,
            argv=["--input.0", "hello", "--input.1.str", "yes", "--input.2", "well"],
            env={},
        )
        assert cfg.input == ["hello", "yes", "well"]

    def test_index_force_cast_pins_first_element(self, loader: ConfargLoader) -> None:
        """``--field.0.str yes`` pins element 0 to the string 'yes' rather than stealing to True."""
        cfg = loader.load(_WithStrBools, argv=["--input.0.str", "yes"], env={})
        assert cfg.input == ["yes"]

    def test_index_into_list_element_patches_not_replaces(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--grid.0.0`` patches the inner list element, not replaces the whole inner list."""
        base = tmp_yaml("grid:\n  - [1, 2, 3]\n  - [4, 5]\n")
        cfg = loader.load(_WithGrid, argv=["--config", str(base), "--grid.0.0", "42"], env={})
        assert cfg.grid == [[42, 2, 3], [4, 5]]

    def test_index_into_tuple_element_patches_not_replaces(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--pairs.0.1`` patches one slot of an inner tuple element, not the whole tuple."""
        base = tmp_yaml("pairs:\n  - [1, 2]\n  - [3, 4]\n")
        cfg = loader.load(_WithPairs, argv=["--config", str(base), "--pairs.0.1", "9"], env={})
        assert cfg.pairs == [(1, 9), (3, 4)]

    def test_tuple_index_set(self, loader: ConfargLoader) -> None:
        """Tuple elements are patchable by index."""
        cfg = loader.load(_WithLang, argv=["--lang.1", "FR"], env={})
        assert cfg.lang == ("en", "FR")

    def test_tuple_negative_index_set(self, loader: ConfargLoader) -> None:
        """A negative index resolves against the fixed tuple length (``-1`` → last slot)."""
        cfg = loader.load(_WithLang, argv=["--lang.-1", "FR"], env={})
        assert cfg.lang == ("en", "FR")

    def test_tuple_build_with_mixed_indices_no_base(self, loader: ConfargLoader) -> None:
        """A fixed tuple builds element-by-element from mixed positive/negative indices."""
        cfg = loader.load(_WithPair, argv=["--input.0", "0", "--input.-1", "1"], env={})
        assert cfg.input == (0, 1)

    def test_tuple_completed_from_shorter_config_base(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A config base shorter than the tuple is completed by an index patch past its end.

        The merge layer cannot tell a list from a fixed tuple, so an index outside the
        base list is deferred to build(), which fills the declared tuple slot instead of
        raising the list replacement-only error.
        """
        base = tmp_yaml("input: [1, 2]\n")
        cfg = loader.load(_WithTriple, argv=["--config", str(base), "--input.2", "3"], env={})
        assert cfg.input == (1, 2, 3)

    def test_list_index_past_config_base_still_errors(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The same out-of-base index on a *list* field still errors (replacement-only).

        Confirms the deferral only relocated the list error to build() — it did not
        weaken list semantics.
        """
        base = tmp_yaml("users: [alice, bob]\n")
        with pytest.raises(ConfargError):
            loader.load(_WithUsers, argv=["--config", str(base), "--users.4", "carol"], env={})

    def test_append_single(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field+ value`` appends one element."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users+", "david"], env={})
        assert cfg.users == ["alice", "bob", "david"]

    def test_delete_index(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field.N-`` removes the element at N."""
        base = tmp_yaml("users: [alice, bob, claire]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.0-"], env={})
        assert cfg.users == ["bob", "claire"]

    def test_delete_negative_index(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Negative-index deletes count from the end."""
        base = tmp_yaml("users: [alice, bob, claire]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.-2-"], env={})
        assert cfg.users == ["alice", "claire"]

    def test_dict_subkey_set(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field.key value`` adds/overrides a dict entry (coerced to the value type)."""
        base = tmp_yaml("data: {a: 1, b: 2}\n")
        cfg = loader.load(_WithMap, argv=["--config", str(base), "--data.c", "3"], env={})
        assert cfg.data == {"a": 1, "b": 2, "c": 3}

    def test_dict_key_delete(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field.key-`` removes a dict entry."""
        base = tmp_yaml("data: {a: 1, b: 2}\n")
        cfg = loader.load(_WithMap, argv=["--config", str(base), "--data.a-"], env={})
        assert cfg.data == {"b": 2}

    def test_interleaved_append_and_patch_newest(self, loader: ConfargLoader) -> None:
        """Append-empty-then-fill-by-(-1) repeats resolve in command order.

        The hardest ordering case: the framework parse result cannot represent
        the two interleaved ``--dbs.-1.dbpath`` patches, so values are read from
        argv in order via the patch scan.
        """
        cfg = loader.load(
            _WithDbs,
            argv=["--dbs+", "{}", "--dbs.-1.dbpath", "db1", "--dbs+", "{}", "--dbs.-1.dbpath", "db2"],
            env={},
        )
        assert cfg.dbs == [_PatchSqlite("db1"), _PatchSqlite("db2")]


class TestCollectionPatchListSyntax:
    """Multi-value appends follow each framework's list-argument convention.

    Whole-field list values keep their framework syntax (space-separated for
    argparse/cyclopts, repeated flags for click); the append/delete ordering on
    top is shared.
    """

    def test_append_multi_space_separated(self, space_sep_loader: ConfargLoader, tmp_yaml) -> None:
        """Space-separated multi-value append (argparse/cyclopts/vanilla)."""
        base = tmp_yaml("users: [john]\n")
        cfg = space_sep_loader.load(_WithUsers, argv=["--config", str(base), "--users+", "billy", "alice"], env={})
        assert cfg.users == ["john", "billy", "alice"]

    def test_append_multi_repeated(self, repeated_loader: ConfargLoader, tmp_yaml) -> None:
        """Repeated-flag multi-value append (click/cyclopts)."""
        base = tmp_yaml("users: [john]\n")
        cfg = repeated_loader.load(
            _WithUsers,
            argv=["--config", str(base), "--users+", "billy", "--users+", "alice"],
            env={},
        )
        assert cfg.users == ["john", "billy", "alice"]

    def test_set_append_delete_order_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """Whole-list set, then append, then delete — applied in command order."""
        cfg = space_sep_loader.load(
            _WithUsers,
            argv=["--users", "john", "--users+", "billy", "alice", "--users.-2-"],
            env={},
        )
        assert cfg.users == ["john", "alice"]

    def test_set_append_delete_order_repeated(self, repeated_loader: ConfargLoader) -> None:
        """Same ordering via click's repeated-flag list syntax."""
        cfg = repeated_loader.load(
            _WithUsers,
            argv=["--users", "john", "--users+", "billy", "--users+", "alice", "--users.-2-"],
            env={},
        )
        assert cfg.users == ["john", "alice"]


# ---------------------------------------------------------------------------
# Expressions over CLI-provided numbers (eager leaf coercion)
# ---------------------------------------------------------------------------


@dataclass
class _ExprConfig:
    """Config whose ``derived`` field is an expression over ``base``."""

    base: int = 0
    derived: int = 0


class TestExpressionOverCliContract:
    """A config expression resolves against a CLI-overridden numeric field in every backend.

    Regression for the deferred-coercion gap: adapters used to leave the CLI
    value as a string, so ``${base * 3}`` raised; eager leaf coercion fixes it.
    """

    def test_expr_references_cli_number(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A CLI int override flows into a config expression and resolves to an int."""
        cfg = tmp_yaml("base: 10\nderived: '${base * 3}'\n")
        result = loader.load(_ExprConfig, argv=["--config", str(cfg), "--base", "8"], env={})
        assert result.base == 8
        assert result.derived == 24


# ---------------------------------------------------------------------------
# Expressions into value-restricted and registered-leaf fields
# ---------------------------------------------------------------------------


class _Colour(Enum):
    """Enum whose members double as the values an expression may resolve to."""

    RED = "red"
    BLUE = "blue"


@dataclass
class _ChoiceConfig:
    """Config pairing a free-form ``name`` with domain-restricted ``lit`` / ``colour``."""

    name: str = "a"
    lit: Literal["a", "b"] = "a"
    colour: _Colour = _Colour.RED


@dataclass
class _LeafConfig:
    """Config whose ``log`` is a registered leaf type (``Path``) fed by an expression."""

    base: str = "/app"
    log: Path = dataclasses.field(default_factory=lambda: Path("."))


class TestExpressionIntoRestrictedFieldContract:
    """A ``${...}`` token reaches a Literal/Enum field through every front-end.

    Regression for the parse-time ``choices`` divergence: the adapters used to
    hand ``FlagSpec.choices`` straight to argparse / ``click.Choice`` /
    ``Literal[...]``, which rejected ``${name}`` before confarg saw it, while
    vanilla (and the env and config-file channels of every front-end) accepted
    it.  An expression's value is unknown until ``resolve_expressions`` runs, so
    the domain check belongs to ``build()``.
    """

    def test_expr_into_literal_field(self, loader: ConfargLoader) -> None:
        """An expression naming another field resolves into a Literal field."""
        cfg = loader.load(_ChoiceConfig, argv=["--name", "b", "--lit", "${name}"], env={})
        assert cfg.lit == "b"

    def test_expr_into_enum_field(self, loader: ConfargLoader) -> None:
        """An expression naming another field resolves into an Enum field."""
        cfg = loader.load(_ChoiceConfig, argv=["--name", "blue", "--colour", "${name}"], env={})
        assert cfg.colour is _Colour.BLUE

    def test_expr_resolving_outside_domain_fails_in_build(self, loader: ConfargLoader) -> None:
        """Deferred, not dropped: an expression resolving off-domain still fails, in build()."""
        with pytest.raises(TypeCoercionError, match="Literal"):
            loader.load(_ChoiceConfig, argv=["--name", "zz", "--lit", "${name}"], env={})

    def test_expr_into_registered_leaf_field(self, loader: ConfargLoader) -> None:
        """An expression survives eager coercion to a registered leaf type (``Path``).

        ``Path("${base}/logs")`` coerces *successfully*, so before the explicit
        expression check in ``_try_coerce`` the token became a ``Path`` that
        ``resolve_expressions`` (which scans ``str`` leaves only) never revisited
        — silently yielding a literal ``${base}/logs`` path.
        """
        cfg = loader.load(_LeafConfig, argv=["--base", "/app", "--log", "${base}/logs"], env={})
        assert cfg.log == Path("/app/logs")

    def test_registered_leaf_expr_matches_config_file_channel(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The CLI, env and config-file channels agree on a leaf-typed expression."""
        cfg_file = tmp_yaml("""
base: /app
log: '${base}/logs'
""")
        from_file = loader.load(_LeafConfig, argv=["--config", str(cfg_file)], env={})
        from_env = loader.load(_LeafConfig, argv=[], env={"X_BASE": "/app", "X_LOG": "${base}/logs"}, env_prefix="X_")
        from_cli = loader.load(_LeafConfig, argv=["--base", "/app", "--log", "${base}/logs"], env={})
        assert from_file.log == from_env.log == from_cli.log == Path("/app/logs")


# ---------------------------------------------------------------------------
# Callable bind on a class __call__ parameter
# ---------------------------------------------------------------------------


class _Greeter:
    """Callable instance: ``greeting`` is a constructor kwarg, ``punct`` a __call__ bind."""

    def __init__(self, greeting: str) -> None:
        self.greeting = greeting

    def __call__(self, name: str, punct: str) -> str:
        return f"{self.greeting}, {name}{punct}"


@dataclass
class _CallableConfig:
    """Config with a single callable field."""

    fn: Callable[[str], str]


class TestCallableBindContract:
    """``--field.bind.<param>`` for a class's ``__call__`` parameter is registered everywhere.

    In ``.class`` mode the constructor params become ``--field.<param>`` factory
    kwargs and the instance's ``__call__`` params become ``--field.bind.<param>``.
    """

    def test_bind_call_param(self, loader: ConfargLoader) -> None:
        """A class chosen via .class binds a __call__ param through --field.bind.<param>."""
        cfg = loader.load(
            _CallableConfig,
            argv=["--fn.class", f"{__name__}._Greeter", "--fn.greeting", "Hi", "--fn.bind.punct", "!"],
            env={},
        )
        assert cfg.fn("world") == "Hi, world!"


# ---------------------------------------------------------------------------
# Escaped directive mode (_fn/_class/_call/_bind) — collision escape, parity across channels
# ---------------------------------------------------------------------------


class _EscBinder:
    """__init__ takes a parameter literally named ``bind``; __call__ takes ``lr``.

    Escaped mode lets the ``__init__`` ``bind`` arg be set (plain ``bind``) while ``_bind``
    partial-applies ``__call__`` — the collision the plain directive names cannot express.
    """

    def __init__(self, bind: int) -> None:
        self.bind = bind

    def __call__(self, lr: int) -> int:
        return self.bind + lr


class _EscOwner:
    """__init__ takes a parameter named ``fn`` (the opener residual), with an instance method."""

    def __init__(self, fn: int) -> None:
        self.fn = fn

    def method(self, x: int) -> int:
        return x + self.fn


@dataclass
class _EscCallableConfig:
    """Config with a bare Callable field (skips arity checks after binding)."""

    fn: Callable


class TestEscapedCallableContract:
    """Escaped directive mode reaches parity across config, env, and CLI (all four front-ends)."""

    def test_compound_init_bind_and_call_bind_via_cli(self, loader: ConfargLoader) -> None:
        """`_class` opener: plain `bind` sets __init__, `_bind.lr` partial-applies __call__."""
        cfg = loader.load(
            _EscCallableConfig,
            argv=["--fn._class", f"{__name__}._EscBinder", "--fn.bind", "5", "--fn._bind.lr", "10"],
            env={},
        )
        assert cfg.fn() == 15  # _EscBinder(bind=5), partial(lr=10) -> 5 + 10

    def test_opener_residual_via_cli(self, loader: ConfargLoader) -> None:
        """`_fn` opener frees a plain `fn` key to be the owning class's constructor kwarg."""
        cfg = loader.load(
            _EscCallableConfig,
            argv=["--fn._fn", f"{__name__}._EscOwner.method", "--fn.fn", "100"],
            env={},
        )
        assert cfg.fn(1) == 101  # _EscOwner(fn=100).method(1) -> 1 + 100

    def test_compound_via_env(self, loader: ConfargLoader) -> None:
        """Env expresses escaped keys via the triple-underscore form (no env code change)."""
        cfg = loader.load(
            _EscCallableConfig,
            argv=[],
            env={
                "APP_FN___CLASS": f"{__name__}._EscBinder",
                "APP_FN__BIND": "5",
                "APP_FN___BIND__LR": "10",
            },
            env_prefix="APP_",
        )
        assert cfg.fn() == 15


# ---------------------------------------------------------------------------
# Explicit .json / __json force-cast
# ---------------------------------------------------------------------------


class TestJsonCastContract:
    """The explicit ``.json`` suffix parses a value as JSON for any field type.

    It is the fifth member of the ``.str``/``.int``/``.float``/``.bool`` cast family:
    an escape hatch that is predictable regardless of the field type and reaches cases
    the implicit two-gate magic cannot (``Any``-typed fields, ``null`` in a list).  A
    real field/dict-key of the same name always wins over the cast.
    """

    def test_struct_field_from_json(self, loader: ConfargLoader) -> None:
        """--db.json '{...}' builds a nested struct."""
        cfg = loader.load(Nested, argv=["--db.json", '{"host": "h", "port": 9}'], env={})
        assert cfg.db == Simple(host="h", port=9)

    def test_list_with_null_from_json(self, loader: ConfargLoader) -> None:
        """--values.json '[null, 5]' passes a None the space-separated syntax can't express."""
        cfg = loader.load(_WithIntNoneList, argv=["--values.json", "[null, 5]"], env={})
        assert cfg.values == [None, 5]

    def test_any_field_only_reachable_via_json(self, loader: ConfargLoader) -> None:
        """.json decodes into an ``Any`` field, which the two-gate magic never touches."""
        cfg = loader.load(_WithAnyField, argv=["--data.json", '{"a": 1}'], env={})
        assert cfg.data == {"a": 1}

    def test_json_null_is_stored_not_dropped(self, loader: ConfargLoader) -> None:
        """--data.json null yields None (the falsy result is not mistaken for 'no cast')."""
        cfg = loader.load(_WithAnyField, argv=["--data.json", "null"], env={})
        assert cfg.data is None

    def test_invalid_json_raises(self, loader: ConfargLoader) -> None:
        """An explicit .json with a malformed value hard-errors (explicit → loud)."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=["--db.json", "not json"], env={})

    def test_real_json_field_wins(self, loader: ConfargLoader) -> None:
        """A field literally named ``json`` is addressed as a field, not a cast."""
        cfg = loader.load(_WithJsonNamedField, argv=["--json", "7"], env={})
        assert cfg.json == 7

    def test_nested_real_json_field_wins(self, loader: ConfargLoader) -> None:
        """--inner.json 3 sets the real sub-field ``json`` rather than casting ``inner``."""
        cfg = loader.load(_OuterInner, argv=["--inner.json", "3"], env={})
        assert cfg.inner.json == 3

    def test_dict_key_named_json(self, loader: ConfargLoader) -> None:
        """On a dict field, --d.json addresses the key ``json`` (a valid key path wins)."""
        cfg = loader.load(_WithDictField, argv=["--d.json", "5"], env={})
        assert cfg.d == {"json": 5}

    def test_merged_dict_is_shared(self, loader: ConfargLoader) -> None:
        """merge() yields the decoded structure raw, identically across every integration."""
        data = loader.merge(Nested, argv=["--db.json", '{"host": "h", "port": 9}'], env={})
        assert data["db"] == {"host": "h", "port": 9}

    def test_bare_object_on_any_is_a_string_via_cli(self, loader: ConfargLoader) -> None:
        """Without .json, a brace value on an Any field stays a string (the magic never guesses)."""
        data = loader.merge(_WithAnyField, argv=["--data", '{"a": 1}'], env={})
        assert data["data"] == '{"a": 1}'

    def test_bare_object_on_any_agrees_across_cli_and_env(self, loader: ConfargLoader) -> None:
        """CLI and env store the identical string for a bare object on an Any field.

        Regression for a divergence where env treated ``Any`` as a struct (via
        ``_is_plain_class(typing.Any)``) and JSON-parsed it while the CLI kept the string.
        """
        cli = loader.merge(_WithAnyField, argv=["--data", '{"a": 1}'], env={})
        env = loader.merge(_WithAnyField, argv=[], env={"MYAPP_DATA": '{"a": 1}'}, env_prefix="MYAPP_")
        assert cli["data"] == env["data"] == '{"a": 1}'


class TestRootJsonContract:
    """A bare ``--json`` injects the whole config at CLI priority: the root peer of ``--field.json``.

    It mirrors the per-field ``.json`` cast for the root object — field flags refine it and a
    real root field named ``json`` still wins (see ``test_real_json_field_wins`` above).
    """

    def test_struct_root_from_json(self, loader: ConfargLoader) -> None:
        """--json '{...}' builds the whole struct root."""
        cfg = loader.load(Nested, argv=["--json", '{"db": {"host": "h", "port": 9}, "debug": true}'], env={})
        assert cfg == Nested(db=Simple(host="h", port=9), debug=True)

    def test_union_root_from_json_structural(self, loader: ConfargLoader) -> None:
        """--json selects a union-root variant by structure, no --class needed."""
        cfg = loader.load(_RootDBConfig, argv=["--json", '{"dbpath": "/tmp/x.db"}'], env={}, config_flag="")
        assert cfg == _RootSQLite(dbpath="/tmp/x.db")

    def test_union_root_from_json_explicit_class(self, loader: ConfargLoader) -> None:
        """--json may carry an explicit class tag for the union root."""
        blob = json.dumps({"class": f"{__name__}._RootSQLite", "dbpath": "/tmp/x.db"})
        cfg = loader.load(_RootDBConfig, argv=["--json", blob], env={}, config_flag="")
        assert cfg == _RootSQLite(dbpath="/tmp/x.db")

    def test_field_flag_overrides_json_either_order(self, loader: ConfargLoader) -> None:
        """A per-field CLI flag wins over --json regardless of argv order."""
        base = '{"db": {"host": "h", "port": 9}}'
        a = loader.load(Nested, argv=["--json", base, "--db.port", "1"], env={})
        b = loader.load(Nested, argv=["--db.port", "1", "--json", base], env={})
        assert a == b == Nested(db=Simple(host="h", port=1))

    def test_json_beats_env(self, loader: ConfargLoader) -> None:
        """Root --json lands at CLI priority, overriding env for the same key."""
        cfg = loader.load(
            Nested,
            argv=["--json", '{"db": {"host": "from-json"}}'],
            env={"MYAPP_DB__HOST": "from-env"},
            env_prefix="MYAPP_",
        )
        assert cfg.db.host == "from-json"

    def test_non_object_for_struct_root_raises(self, loader: ConfargLoader) -> None:
        """A non-object --json for a structured target is rejected."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=["--json", "[1, 2]"], env={})

    def test_invalid_json_raises(self, loader: ConfargLoader) -> None:
        """A malformed root --json hard-errors (explicit → loud)."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=["--json", "{bad"], env={})

    def test_merged_dict_is_shared(self, loader: ConfargLoader) -> None:
        """merge() folds the decoded object into the raw dict identically across integrations."""
        data = loader.merge(Nested, argv=["--json", '{"db": {"host": "h", "port": 9}}'], env={})
        assert data["db"] == {"host": "h", "port": 9}


class TestEnvJsonCastContract:
    """The env counterpart ``FOO__field__json`` mirrors the CLI ``.json`` suffix."""

    def test_env_struct_from_json(self, loader: ConfargLoader) -> None:
        """MYAPP_DB__json='{...}' builds a nested struct from env."""
        cfg = loader.load(
            Nested,
            argv=[],
            env={"MYAPP_DB__json": '{"host": "eh", "port": 1}'},
            env_prefix="MYAPP_",
        )
        assert cfg.db == Simple(host="eh", port=1)

    def test_env_invalid_json_raises(self, loader: ConfargLoader) -> None:
        """A malformed __json env value hard-errors, matching the CLI."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=[], env={"MYAPP_DB__json": "nope"}, env_prefix="MYAPP_")

    def test_env_real_json_field_wins(self, loader: ConfargLoader) -> None:
        """MYAPP_INNER__json sets the real ``json`` sub-field, not a cast on ``inner``."""
        cfg = loader.load(_OuterInner, argv=[], env={"MYAPP_INNER__json": "9"}, env_prefix="MYAPP_")
        assert cfg.inner.json == 9

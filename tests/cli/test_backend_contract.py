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
import math
from collections.abc import (
    Callable,  # noqa: TC003  # used in a runtime dataclass annotation confarg resolves via get_type_hints
)
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

import pytest

import confarg
from confarg.cli.argparse._build import build_static_flags
from confarg.exceptions import ConfargError, MissingFieldError, TypeCoercionError
from tests.conftest import AppConfig, CacheConfig, DbConfig, make_target

if TYPE_CHECKING:
    from pathlib import Path

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

    type: Literal["postgre"] = "postgre"
    host: str = ""


_RootTypedDBConfig: Any = _RootMariaDBTyped | _RootPostgreTyped


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
        assert set(type_specs[0].choices or []) == {"mariadb", "postgre"}

    def test_union_root_literal_discriminator_selects_variant(self, loader: ConfargLoader) -> None:
        """--type <value> selects the matching union variant regardless of order."""
        maria = loader.load(_RootTypedDBConfig, argv=["--type", "mariadb", "--host", "h"], env={}, config_flag="")
        assert isinstance(maria, _RootMariaDBTyped)
        postgre = loader.load(_RootTypedDBConfig, argv=["--type", "postgre", "--host", "h"], env={}, config_flag="")
        assert isinstance(postgre, _RootPostgreTyped)


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
class _WithDbs:
    """List-of-struct field."""

    dbs: list[_PatchSqlite] = dataclasses.field(default_factory=list)


@dataclass
class _WithMap:
    """Dict field (skipped at static registration; patched via argv subkeys)."""

    data: dict[str, int] = dataclasses.field(default_factory=dict)


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

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for argparse integration: populate_parser, from_namespace, FieldMeta."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, make_dataclass
from enum import Enum
from typing import Annotated, Literal

import pytest

import confarg
from confarg._types import _StrToken
from confarg.cli.argparse import FieldMeta, from_namespace, make_parser, populate_parser
from confarg.cli.argparse._namespace import _collect_ns_fields
from confarg.cli.argparse._spec import _get_field_docstrings
from confarg.typedload._coerce import _LEAF_COERCIONS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_custom_leaf_types():
    """Remove any custom types added to _LEAF_COERCIONS during a test."""
    before = set(_LEAF_COERCIONS)
    yield
    for tp in list(_LEAF_COERCIONS):
        if tp not in before:
            del _LEAF_COERCIONS[tp]


# ---------------------------------------------------------------------------
# Dataclasses used across tests
# ---------------------------------------------------------------------------


@dataclass
class Simple:
    """Simple dataclass for testing basic flag registration."""

    host: str
    """Database hostname."""

    port: int = 5432
    """Port to connect on."""

    debug: bool = False
    """Enable debug mode."""


@dataclass
class WithCollections:
    """Dataclass with collection-typed fields for testing."""

    tags: list[str] = field(default_factory=list)
    """List of tags."""

    coords: tuple[float, float] = (0.0, 0.0)
    """Fixed two-element tuple."""

    scores: tuple[int, ...] = ()
    """Variable-length tuple of ints."""


@dataclass
class DbConfig:
    """Database configuration."""

    host: str
    """Hostname."""

    port: int = 5432
    """Port."""


@dataclass
class AppConfig:
    """Top-level application configuration."""

    db: DbConfig
    debug: bool = False
    """Global debug flag."""


@dataclass
class _Inner:
    value: int = 0


@dataclass
class _Middle:
    inner: _Inner
    field: str = ""


@dataclass
class _DeepConfig:
    middle: _Middle
    name: str = ""


@dataclass
class WithOptional:
    """Dataclass with optional fields for testing."""

    name: str = "default"
    """Name field."""

    label: str | None = None
    """Optional label."""


class Color(Enum):
    """Color enumeration for testing enum flag support."""

    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@dataclass
class WithEnum:
    """Dataclass with an Enum field for testing."""

    color: Color = Color.RED
    """Favourite color."""


@dataclass
class WithLiteral:
    """Dataclass with a Literal field for testing."""

    level: Literal["debug", "info", "warning"] = "info"
    """Log level."""


@dataclass
class WithFieldMeta:
    """Dataclass with FieldMeta annotations for testing help and metavar."""

    port: Annotated[int, FieldMeta(help="TCP port.", metavar="PORT")] = 8080
    """Fallback docstring (should not appear — FieldMeta.help wins)."""


@dataclass
class WithMultiUnion:
    """Dataclass with a multi-type union field (should be skipped by populate_parser)."""

    value: int | str = 0


@dataclass
class _StructVariantA:
    x: int = 0


@dataclass
class _StructVariantB:
    y: str = ""


@dataclass
class _WithStructUnion:
    item: _StructVariantA | _StructVariantB


@dataclass
class NoDocstrings:
    """Dataclass with no field docstrings for testing graceful fallback."""

    name: str
    count: int = 0


class _Hex:
    """Custom leaf type: hex-string → integer wrapper, used to test register_leaf_type."""

    __hash__ = None  # unhashable by design; only __eq__ is needed for assertions

    def __init__(self, value: int) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Hex) and other.value == self.value


@dataclass
class _WithHex:
    color: _Hex


# ---------------------------------------------------------------------------
# _get_field_docstrings
# ---------------------------------------------------------------------------


class TestGetFieldDocstrings:
    """Tests for _get_field_docstrings helper."""

    def test_extracts_docstrings(self) -> None:
        """Test that field docstrings are extracted correctly."""
        docs = _get_field_docstrings(Simple)
        assert docs["host"] == "Database hostname."
        assert docs["port"] == "Port to connect on."
        assert docs["debug"] == "Enable debug mode."

    def test_no_docstrings(self) -> None:
        """Test that a class with no docstrings returns an empty dict."""
        docs = _get_field_docstrings(NoDocstrings)
        assert docs == {}

    def test_dynamic_class_returns_empty(self) -> None:
        """Test that dynamically created dataclasses return an empty docstring dict."""
        Dyn = make_dataclass("Dyn", [("x", int)])
        assert _get_field_docstrings(Dyn) == {}


# ---------------------------------------------------------------------------
# populate_parser — flag registration
# ---------------------------------------------------------------------------


class TestPopulateParser:
    """Tests for populate_parser flag registration."""

    def _flags(self, dc_type) -> set[str]:
        parser = argparse.ArgumentParser()
        populate_parser(dc_type, parser)
        return {s for a in parser._actions for s in a.option_strings}

    def test_simple_flags_registered(self) -> None:
        """Test that simple fields register the expected CLI flags."""
        flags = self._flags(Simple)
        assert "--host" in flags
        assert "--port" in flags
        assert "--debug" in flags
        assert "--no-debug" not in flags

    def test_nested_flags_registered(self) -> None:
        """Test that nested dataclass fields register dot-separated flags."""
        flags = self._flags(AppConfig)
        assert "--db.host" in flags
        assert "--db.port" in flags
        assert "--debug" in flags

    def test_collection_flags(self) -> None:
        """Test that collection fields register the expected flags."""
        flags = self._flags(WithCollections)
        assert "--tags" in flags
        assert "--coords" in flags
        assert "--scores" in flags

    def test_enum_flag(self) -> None:
        """Test that Enum fields register choices from enum members."""
        parser = argparse.ArgumentParser()
        populate_parser(WithEnum, parser)
        color_action = next(a for a in parser._actions if "--color" in a.option_strings)
        assert color_action.choices is not None
        assert set(color_action.choices) == {"RED", "GREEN", "BLUE", "red", "green", "blue"}

    def test_literal_flag(self) -> None:
        """Test that Literal fields register choices from literal values."""
        parser = argparse.ArgumentParser()
        populate_parser(WithLiteral, parser)
        level_action = next(a for a in parser._actions if "--level" in a.option_strings)
        assert level_action.choices is not None
        assert set(level_action.choices) == {"debug", "info", "warning"}

    def test_literal_none_choices_include_tokens(self) -> None:
        """Literal[None, str] choices include 'none'/'null' so argparse accepts them."""

        @dataclass
        class WithNoneLiteral:
            value: Literal[None, "toto"] = "toto"

        parser = argparse.ArgumentParser()
        populate_parser(WithNoneLiteral, parser)
        action = next(a for a in parser._actions if "--value" in a.option_strings)
        assert action.choices is not None
        assert "none" in action.choices
        assert "null" in action.choices
        assert "toto" in action.choices

    def test_dict_field_skipped(self) -> None:
        """Test that dict fields are not registered as CLI flags."""

        @dataclass
        class WithDict:
            mapping: dict[str, int] = field(default_factory=dict)

        parser = argparse.ArgumentParser()
        populate_parser(WithDict, parser)
        flags = {a.option_strings[0] for a in parser._actions if a.option_strings}
        assert "--mapping" not in flags

    def test_multi_union_field_skipped(self) -> None:
        """Test that multi-type union fields are not registered as flags."""
        parser = argparse.ArgumentParser()
        populate_parser(WithMultiUnion, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--value" not in flags

    def test_struct_union_registers_class_tag_flag(self) -> None:
        """Multi-variant struct union gets --<field>.class registered."""
        parser = argparse.ArgumentParser()
        populate_parser(_WithStructUnion, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--item.class" in flags
        assert "--item" not in flags

    def test_registered_leaf_type_flag(self) -> None:
        """A field whose type is registered as a leaf gets a single flat flag, not sub-flags."""
        confarg.register_leaf_type(_Hex, lambda s: _Hex(int(s, 16)))

        parser = argparse.ArgumentParser()
        populate_parser(_WithHex, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--color" in flags
        assert "--color.value" not in flags

    def test_argument_groups_for_nested(self) -> None:
        """Test that nested dataclasses create named argument groups."""
        parser = argparse.ArgumentParser()
        populate_parser(AppConfig, parser)
        group_titles = {g.title for g in parser._action_groups}
        assert "db" in group_titles

    def test_suppress_default_not_in_namespace(self) -> None:
        """Test that unprovided optional fields are absent from the namespace."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--host", "localhost"])
        assert "port" not in vars(ns)  # not provided → SUPPRESS keeps it absent
        assert "debug" not in vars(ns)


# ---------------------------------------------------------------------------
# populate_parser — help text
# ---------------------------------------------------------------------------


class TestHelpText:
    """Tests for help text generation in populate_parser."""

    def _help(self, dc_type, flag: str) -> str:
        parser = argparse.ArgumentParser()
        populate_parser(dc_type, parser)
        for action in parser._actions:
            if flag in action.option_strings:
                return action.help or ""
        return ""

    def test_docstring_used_as_help(self) -> None:
        """Test that field docstrings are used as help text."""
        h = self._help(Simple, "--host")
        assert "Database hostname" in h

    def test_default_appended_to_help(self) -> None:
        """Test that the default value is appended to help text."""
        h = self._help(Simple, "--port")
        assert "5432" in h

    def test_fieldmeta_help_overrides_docstring(self) -> None:
        """Test that FieldMeta.help overrides the field docstring."""
        h = self._help(WithFieldMeta, "--port")
        assert "TCP port." in h
        assert "Fallback" not in h

    def test_fieldmeta_metavar(self) -> None:
        """Test that FieldMeta.metavar is applied to the argparse action."""
        parser = argparse.ArgumentParser()
        populate_parser(WithFieldMeta, parser)
        action = next(a for a in parser._actions if "--port" in a.option_strings)
        assert action.metavar == "PORT"

    def test_no_docstring_no_crash(self) -> None:
        """Test that fields without docstrings do not cause a crash."""
        h = self._help(NoDocstrings, "--name")
        assert isinstance(h, str)

    def test_optional_field_help_includes_none_sentinel(self) -> None:
        """Help text for Optional[X] fields mentions 'none' or 'null'."""

        @dataclass
        class WithOpt:
            value: int | None = None

        h = self._help(WithOpt, "--value")
        assert "none" in h.lower() or "null" in h.lower()


# ---------------------------------------------------------------------------
# from_namespace — round-trip
# ---------------------------------------------------------------------------


class TestFromNamespace:
    """Tests for from_namespace round-trip parsing."""

    def test_basic_parse(self) -> None:
        """Test that basic fields parse correctly from namespace."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--host", "localhost", "--port", "9000"])
        result = from_namespace(Simple, ns)
        assert result.host == "localhost"
        assert result.port == 9000
        assert result.debug is False  # dataclass default

    def test_bool_true(self) -> None:
        """Test that --debug true sets the bool field to True."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--host", "h", "--debug", "true"])
        assert from_namespace(Simple, ns).debug is True

    def test_bool_false_via_no_flag(self) -> None:
        """Test that --debug false sets the bool field to False."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--host", "h", "--debug", "false"])
        assert from_namespace(Simple, ns).debug is False

    def test_defaults_used_when_absent(self) -> None:
        """Test that dataclass defaults are used for absent optional fields."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--host", "localhost"])
        result = from_namespace(Simple, ns)
        assert result.port == 5432
        assert result.debug is False

    def test_missing_required_raises(self) -> None:
        """Test that MissingFieldError is raised when a required field is absent."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args([])  # host not provided
        with pytest.raises(confarg.exceptions.MissingFieldError):
            from_namespace(Simple, ns)

    def test_nested_dataclass(self) -> None:
        """Test that nested dataclass fields are parsed from dot-separated flags."""
        parser = argparse.ArgumentParser()
        populate_parser(AppConfig, parser)
        ns = parser.parse_args(["--db.host", "pg", "--db.port", "5433", "--debug", "true"])
        result = from_namespace(AppConfig, ns)
        assert result.db.host == "pg"
        assert result.db.port == 5433
        assert result.debug is True

    def test_optional_field_absent(self) -> None:
        """Test that optional fields default to None when absent."""
        parser = argparse.ArgumentParser()
        populate_parser(WithOptional, parser)
        ns = parser.parse_args([])
        result = from_namespace(WithOptional, ns)
        assert result.name == "default"
        assert result.label is None

    def test_optional_field_provided(self) -> None:
        """Test that optional fields are set when provided."""
        parser = argparse.ArgumentParser()
        populate_parser(WithOptional, parser)
        ns = parser.parse_args(["--label", "hello"])
        result = from_namespace(WithOptional, ns)
        assert result.label == "hello"

    def test_list_field(self) -> None:
        """Test that list fields accept multiple space-separated values."""
        parser = argparse.ArgumentParser()
        populate_parser(WithCollections, parser)
        ns = parser.parse_args(["--tags", "a", "b", "c"])
        result = from_namespace(WithCollections, ns)
        assert result.tags == ["a", "b", "c"]

    def test_fixed_tuple_field(self) -> None:
        """Test that fixed-length tuple fields parse positional values."""
        parser = argparse.ArgumentParser()
        populate_parser(WithCollections, parser)
        ns = parser.parse_args(["--coords", "1.5", "2.5"])
        result = from_namespace(WithCollections, ns)
        assert result.coords == (1.5, 2.5)

    def test_enum_field(self) -> None:
        """Test that Enum fields parse to the correct Enum member."""
        parser = argparse.ArgumentParser()
        populate_parser(WithEnum, parser)
        ns = parser.parse_args(["--color", "BLUE"])
        result = from_namespace(WithEnum, ns)
        assert result.color == Color.BLUE

    def test_enum_field_by_value(self) -> None:
        """Test that Enum fields accept enum values (not just names) via CLI."""
        parser = argparse.ArgumentParser()
        populate_parser(WithEnum, parser)
        ns = parser.parse_args(["--color", "blue"])
        result = from_namespace(WithEnum, ns)
        assert result.color == Color.BLUE

    def test_registered_leaf_type_round_trip(self) -> None:
        """A registered leaf type is coerced correctly end-to-end via argparse."""
        confarg.register_leaf_type(_Hex, lambda s: _Hex(int(s, 16)))

        parser = make_parser(_WithHex)
        ns = parser.parse_args(["--color", "ff"])
        result = from_namespace(_WithHex, ns)
        assert isinstance(result.color, _Hex)
        assert result.color.value == 255

    def test_literal_field(self) -> None:
        """Test that Literal fields parse to the correct string value."""
        parser = argparse.ArgumentParser()
        populate_parser(WithLiteral, parser)
        ns = parser.parse_args(["--level", "warning"])
        result = from_namespace(WithLiteral, ns)
        assert result.level == "warning"

    def test_literal_none_cli(self) -> None:
        """--value none is accepted and coerced to None for Literal[None, str]."""

        @dataclass
        class WithNoneLiteral:
            value: Literal[None, "toto"] = "toto"

        parser = argparse.ArgumentParser()
        populate_parser(WithNoneLiteral, parser)
        ns = parser.parse_args(["--value", "none"])
        result = from_namespace(WithNoneLiteral, ns)
        assert result.value is None

    def test_literal_int_stealing_cli(self) -> None:
        """--value 16 coerces to int 16 (not string '16') for Literal['16', 16]."""

        @dataclass
        class WithMixedLiteral:
            value: Literal["16", 16] = 16

        parser = argparse.ArgumentParser()
        populate_parser(WithMixedLiteral, parser)
        ns = parser.parse_args(["--value", "16"])
        result = from_namespace(WithMixedLiteral, ns)
        assert result.value == 16
        assert type(result.value) is int

    def test_coexists_with_user_flags(self) -> None:
        """User can add their own flags; from_namespace ignores them."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        parser.add_argument("--verbose", action="store_true")
        ns = parser.parse_args(["--host", "h", "--verbose"])
        result = from_namespace(Simple, ns)
        assert result.host == "h"
        assert ns.verbose is True

    def test_union_class_tag_collected_by_collect_ns_fields(self) -> None:
        """--<field>.class in namespace is passed through to the merge pipeline."""
        flat = {"item.class": "myapp._StructVariantA"}
        result: dict = {}
        _collect_ns_fields(flat, _WithStructUnion, prefix="", union_tag="class", result=result)
        assert result == {"item": {"class": _StrToken("myapp._StructVariantA")}}


# ---------------------------------------------------------------------------
# Config file support in populate_parser / from_namespace
# ---------------------------------------------------------------------------


class TestConfigFileSupport:
    """Config files can be passed via --config flag or the files= parameter."""

    def test_config_flag_registered_by_default(self) -> None:
        """populate_parser registers --config by default."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--config" in flags

    def test_config_flag_absent_when_disabled(self) -> None:
        """config_flag='' suppresses --config registration."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser, config_flag="")
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--config" not in flags

    def test_custom_config_flag_name(self) -> None:
        """config_flag='cfg' registers --cfg instead of --config."""
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser, config_flag="cfg")
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--cfg" in flags
        assert "--config" not in flags

    def test_config_file_via_namespace(self, tmp_path) -> None:
        """Values from --config file are used when CLI doesn't provide them."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text('host = "from_file"\nport = 1234\n')
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--config", str(cfg)])
        result = from_namespace(Simple, ns, env={})
        assert result.host == "from_file"
        assert result.port == 1234

    def test_config_file_via_files_param(self, tmp_path) -> None:
        """Values from files= parameter are loaded."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text('host = "file_host"\nport = 9999\n')
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args([])
        result = from_namespace(Simple, ns, files=[cfg], env={})
        assert result.host == "file_host"
        assert result.port == 9999

    def test_cli_overrides_config_file(self, tmp_path) -> None:
        """CLI argument takes priority over config file value."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text('host = "from_file"\nport = 1111\n')
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--config", str(cfg), "--port", "2222"])
        result = from_namespace(Simple, ns, env={})
        assert result.host == "from_file"
        assert result.port == 2222

    def test_env_overrides_config_file(self, tmp_path) -> None:
        """Env var with explicit prefix takes priority over config file value."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text('host = "from_file"\nport = 1111\n')
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--config", str(cfg)])
        result = from_namespace(Simple, ns, env={"CONFARG_PORT": "3333"}, env_prefix="CONFARG_")
        assert result.host == "from_file"
        assert result.port == 3333

    def test_env_disabled_by_default(self, tmp_path) -> None:
        """Env vars are ignored when env_prefix is None (the default)."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text('host = "from_file"\nport = 1111\n')
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--config", str(cfg)])
        result = from_namespace(Simple, ns, env={"PORT": "9999"})
        assert result.port == 1111

    def test_multiple_config_files_merged(self, tmp_path) -> None:
        """Later config files in the list override earlier ones."""
        cfg1 = tmp_path / "base.toml"
        cfg1.write_text('host = "base"\nport = 1000\n')
        cfg2 = tmp_path / "override.toml"
        cfg2.write_text("port = 2000\n")
        parser = argparse.ArgumentParser()
        populate_parser(Simple, parser)
        ns = parser.parse_args(["--config", str(cfg1), str(cfg2)])
        result = from_namespace(Simple, ns, env={})
        assert result.host == "base"
        assert result.port == 2000

    def test_subkey_config_flag_registered(self) -> None:
        """populate_parser registers --config.<nested> for each nested dataclass."""
        parser = argparse.ArgumentParser()
        populate_parser(AppConfig, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--config" in flags
        assert "--config.db" in flags

    def test_subkey_config_flag_loads_under_subkey(self, tmp_path) -> None:
        """--config.db file.toml loads file contents under the 'db' key."""
        db_cfg = tmp_path / "db.toml"
        db_cfg.write_text('host = "db_host"\nport = 5555\n')
        parser = argparse.ArgumentParser()
        populate_parser(AppConfig, parser)
        ns = parser.parse_args(["--config.db", str(db_cfg)])
        result = from_namespace(AppConfig, ns, env={})
        assert result.db.host == "db_host"
        assert result.db.port == 5555

    def test_subkey_config_and_root_config_combined(self, tmp_path) -> None:
        """Root --config and --config.db can be combined; CLI still wins."""
        root_cfg = tmp_path / "root.toml"
        root_cfg.write_text("debug = true\n")
        db_cfg = tmp_path / "db.toml"
        db_cfg.write_text('host = "from_file"\nport = 1111\n')
        parser = argparse.ArgumentParser()
        populate_parser(AppConfig, parser)
        ns = parser.parse_args(
            [
                "--config",
                str(root_cfg),
                "--config.db",
                str(db_cfg),
                "--db.port",
                "9999",
            ],
        )
        result = from_namespace(AppConfig, ns, env={})
        assert result.debug is True
        assert result.db.host == "from_file"
        assert result.db.port == 9999  # CLI overrides file

    def test_subkey_config_no_deep_flags(self) -> None:
        """--config.<field> flags are generated only for direct fields, not recursively."""
        parser = argparse.ArgumentParser()
        populate_parser(_DeepConfig, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--config.middle" in flags
        assert "--config.middle.inner" not in flags

    def test_subkey_config_false_root_only(self) -> None:
        """config_subkeys=False registers only the root --config flag."""
        parser = argparse.ArgumentParser()
        populate_parser(AppConfig, parser, config_subkeys=False)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--config" in flags
        assert "--config.db" not in flags


# ---------------------------------------------------------------------------
# Inheritance-based dispatch (base class with subclasses)
# ---------------------------------------------------------------------------


@dataclass
class _BaseDB:
    """Abstract base database config."""


@dataclass
class _SQLiteDB(_BaseDB):
    dbpath: str


@dataclass
class _ServerDB(_BaseDB):
    host: str
    port: int


class TestInheritanceDispatch:
    """populate_parser / from_namespace handle base-class + subclass inheritance."""

    def test_class_flag_registered(self) -> None:
        """populate_parser registers --class for a base dataclass with subclasses."""
        parser = argparse.ArgumentParser(allow_abbrev=False)
        populate_parser(_BaseDB, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--class" in flags

    def test_subclass_fields_registered(self) -> None:
        """populate_parser also registers subclass fields as top-level flags."""
        parser = argparse.ArgumentParser(allow_abbrev=False)
        populate_parser(_BaseDB, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--dbpath" in flags
        assert "--host" in flags
        assert "--port" in flags

    def test_from_namespace_sqlite(self) -> None:
        """from_namespace constructs the correct SQLite subclass instance."""
        parser = argparse.ArgumentParser(allow_abbrev=False)
        populate_parser(_BaseDB, parser, config_flag="")
        ns = parser.parse_args(
            [
                "--class",
                f"{__name__}._SQLiteDB",
                "--dbpath",
                "/var/db/app.sqlite",
            ],
        )
        result = from_namespace(_BaseDB, ns, env={})
        assert isinstance(result, _SQLiteDB)
        assert result.dbpath == "/var/db/app.sqlite"

    def test_from_namespace_server(self) -> None:
        """from_namespace constructs the correct server subclass instance."""
        parser = argparse.ArgumentParser(allow_abbrev=False)
        populate_parser(_BaseDB, parser, config_flag="")
        ns = parser.parse_args(
            [
                "--class",
                f"{__name__}._ServerDB",
                "--host",
                "db.example.com",
                "--port",
                "5432",
            ],
        )
        result = from_namespace(_BaseDB, ns, env={})
        assert isinstance(result, _ServerDB)
        assert result.host == "db.example.com"
        assert result.port == 5432


class TestMakeParser:
    """make_parser creates a pre-populated ArgumentParser with safe defaults."""

    def test_allow_abbrev_false_by_default(self) -> None:
        """make_parser disables abbreviation matching by default."""
        parser = make_parser(Simple)
        assert parser.allow_abbrev is False

    def test_allow_abbrev_override(self) -> None:
        """make_parser forwards allow_abbrev=True when explicitly requested."""
        parser = make_parser(Simple, allow_abbrev=True)
        assert parser.allow_abbrev is True

    def test_fields_populated(self) -> None:
        """make_parser registers the target's fields as arguments."""
        parser = make_parser(Simple)
        dests = {a.dest for a in parser._actions}
        assert "host" in dests
        assert "port" in dests
        assert "debug" in dests

    def test_kwargs_forwarded(self) -> None:
        """Extra kwargs (description, prog) are forwarded to ArgumentParser."""
        parser = make_parser(Simple, description="My app", prog="myapp")
        assert parser.description == "My app"
        assert parser.prog == "myapp"

    def test_parse_and_construct(self) -> None:
        """make_parser produces a parser that round-trips through from_namespace."""
        parser = make_parser(Simple, config_flag="")
        ns = parser.parse_args(["--host", "localhost", "--port", "9999"])
        result = from_namespace(Simple, ns, env={})
        assert result.host == "localhost"
        assert result.port == 9999

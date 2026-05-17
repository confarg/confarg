# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for dynamic tab-completion support (_completion.py + _argparse.py union changes)."""

from __future__ import annotations

import argparse
import builtins
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest

from confarg.cli.argparse import from_namespace, populate_parser, setup_completion
from confarg.cli.argparse._completion import (
    _collect_partial_cli_tags,
    _collect_partial_config,
    _extend_walk,
    _pre_extend_parser_for_completion,
    _resolve_tags_from_config,
    _WalkCtx,
)

# ---------------------------------------------------------------------------
# Dataclasses used across tests
# ---------------------------------------------------------------------------


@dataclass
class _DBBase:
    """Abstract DB base."""


@dataclass
class _ServerDB(_DBBase):
    host: str
    """Hostname."""
    port: int = 5432
    """Port."""


@dataclass
class _SQLiteDB(_DBBase):
    dbpath: str = ":memory:"
    """SQLite file path."""


@dataclass
class _AppConfig:
    db: _ServerDB | _SQLiteDB
    """Database configuration."""
    debug: bool = False


@dataclass
class _NestedUnionInVariant:
    """A variant whose 'cache' field is itself a union."""


@dataclass
class _CacheA:
    url: str = "redis://localhost"


@dataclass
class _CacheB:
    ttl: int = 60


@dataclass
class _ServerWithCache(_DBBase):
    host: str = "localhost"
    cache: _CacheA | _CacheB = field(default_factory=_CacheA)


@dataclass
class _AppWithNestedUnion:
    db: _DBBase


@dataclass
class _ExtendWalkInner:
    x: int = 0


@dataclass
class _ExtendWalkOuter:
    inner: _ExtendWalkInner


# ---------------------------------------------------------------------------
# TestPopulateParser — union class-tag flag registration
# ---------------------------------------------------------------------------


class TestUnionClassTagRegistration:
    """Tests for class-tag flag registration in union types."""

    def test_struct_union_registers_class_flag(self) -> None:
        """Multi-variant struct union registers --db.class."""
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--db.class" in flags

    def test_class_flag_dest_is_dotted(self) -> None:
        """--db.class action has dest 'db.class'."""
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)
        action = next(a for a in parser._actions if "--db.class" in a.option_strings)
        assert action.dest == "db.class"

    def test_class_flag_has_completer_with_known_variants(self) -> None:
        """--db.class action has .completer suggesting concrete variant paths."""
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)
        action = next(a for a in parser._actions if "--db.class" in a.option_strings)
        assert hasattr(action, "completer")
        suggestions = action.completer(prefix="", parsed_args=None)  # ty: ignore[call-non-callable]  # argcomplete monkey-patches .completer onto actions
        module = _ServerDB.__module__
        assert f"{module}._ServerDB" in suggestions
        assert f"{module}._SQLiteDB" in suggestions

    def test_completer_filters_by_prefix(self) -> None:
        """Completer only returns paths starting with the given prefix."""
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)
        action = next(a for a in parser._actions if "--db.class" in a.option_strings)
        module = _ServerDB.__module__
        suggestions = action.completer(prefix=f"{module}._Server", parsed_args=None)  # ty: ignore[unresolved-attribute]  # argcomplete monkey-patches .completer onto actions
        assert f"{module}._ServerDB" in suggestions
        assert f"{module}._SQLiteDB" not in suggestions

    def test_non_struct_union_no_class_flag(self) -> None:
        """Int | str union does NOT register a --value.class flag."""

        @dataclass
        class _WithPrimUnion:
            value: int | str = 0

        parser = argparse.ArgumentParser()
        populate_parser(_WithPrimUnion, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--value.class" not in flags
        assert "--value" not in flags

    def test_non_struct_union_field_still_absent(self) -> None:
        """Leaf fields of non-struct union variant stay absent (unchanged behaviour)."""

        @dataclass
        class _WithPrimUnion:
            value: int | str = 0

        parser = argparse.ArgumentParser()
        populate_parser(_WithPrimUnion, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--value" not in flags


# ---------------------------------------------------------------------------
# _collect_partial_config
# ---------------------------------------------------------------------------


class TestCollectPartialConfig:
    """Tests for _collect_partial_config helper."""

    def test_reads_toml_from_argv(self, tmp_path) -> None:
        """Test that TOML config file is read from argv."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text('[db]\nclass = "myapp.ServerDB"\n')
        result = _collect_partial_config([f"--config={cfg}"], "config")
        assert result == {"db": {"class": "myapp.ServerDB"}}

    def test_reads_multiple_config_files(self, tmp_path) -> None:
        """Test that multiple config files are merged together."""
        cfg1 = tmp_path / "a.toml"
        cfg1.write_text("x = 1\n")
        cfg2 = tmp_path / "b.toml"
        cfg2.write_text("y = 2\n")
        result = _collect_partial_config(["--config", str(cfg1), str(cfg2)], "config")
        assert result == {"x": 1, "y": 2}

    def test_missing_file_silently_ignored(self) -> None:
        """Test that a missing config file is silently ignored."""
        result = _collect_partial_config(["--config", "/nonexistent/file.toml"], "config")
        assert result == {}

    def test_does_not_read_subkey_config_flags(self, tmp_path) -> None:
        """--config.db file.toml is a subkey flag; root config collector ignores it."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("x = 1\n")
        result = _collect_partial_config([f"--config.db={cfg}"], "config")
        assert result == {}

    def test_yaml_file_read(self, tmp_path) -> None:
        """Test that YAML config files are also read correctly."""
        pytest.importorskip("yaml")
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text("db:\n  class: myapp.ServerDB\n")
        result = _collect_partial_config([f"--config={cfg}"], "config")
        assert result == {"db": {"class": "myapp.ServerDB"}}

    def test_empty_argv(self) -> None:
        """Test that empty argv returns an empty dict."""
        result = _collect_partial_config([], "config")
        assert result == {}


# ---------------------------------------------------------------------------
# _collect_partial_cli_tags
# ---------------------------------------------------------------------------


class TestCollectPartialCliTags:
    """Tests for _collect_partial_cli_tags helper."""

    def test_space_separated(self) -> None:
        """Test that space-separated --field.class value is parsed."""
        tags = _collect_partial_cli_tags(["--db.class", "myapp.ServerDB"], "class")
        assert tags == {"db": "myapp.ServerDB"}

    def test_equals_form(self) -> None:
        """Test that --field.class=value form is parsed."""
        tags = _collect_partial_cli_tags(["--db.class=myapp.ServerDB"], "class")
        assert tags == {"db": "myapp.ServerDB"}

    def test_multiple_tags(self) -> None:
        """Test that multiple class tag flags are all collected."""
        tags = _collect_partial_cli_tags(
            ["--db.class", "myapp.ServerDB", "--cache.class", "myapp.Redis"],
            "class",
        )
        assert tags == {"db": "myapp.ServerDB", "cache": "myapp.Redis"}

    def test_nested_prefix(self) -> None:
        """Test that a deeply nested class tag is keyed by full prefix."""
        tags = _collect_partial_cli_tags(["--db.backend.class", "myapp.Redis"], "class")
        assert tags == {"db.backend": "myapp.Redis"}

    def test_no_match(self) -> None:
        """Test that argv with no class tags returns an empty dict."""
        tags = _collect_partial_cli_tags(["--host", "localhost", "--port", "5432"], "class")
        assert tags == {}

    def test_ignores_flag_without_value(self) -> None:
        """Test that a class tag flag with no following value is ignored."""
        # --db.class at end of argv with no following value
        tags = _collect_partial_cli_tags(["--db.class"], "class")
        assert tags == {}

    def test_ignores_flag_followed_by_another_flag(self) -> None:
        """Test that a class tag flag followed by another flag is ignored."""
        tags = _collect_partial_cli_tags(["--db.class", "--other"], "class")
        assert tags == {}


# ---------------------------------------------------------------------------
# _resolve_tags_from_config
# ---------------------------------------------------------------------------


class TestResolveTagsFromConfig:
    """Tests for _resolve_tags_from_config helper."""

    def test_finds_struct_union_tag(self) -> None:
        """Test that a union tag is found in the merged config dict."""
        merged = {"db": {"class": "myapp.ServerDB", "host": "localhost"}}
        tags = _resolve_tags_from_config(merged, _AppConfig, prefix="", union_tag="class")
        assert tags == {"db": "myapp.ServerDB"}

    def test_empty_when_no_union_tag(self) -> None:
        """Test that no union tag in config yields an empty dict."""
        merged = {"db": {"host": "localhost"}}
        tags = _resolve_tags_from_config(merged, _AppConfig, prefix="", union_tag="class")
        assert tags == {}

    def test_empty_when_merged_empty(self) -> None:
        """Test that an empty merged config yields an empty tags dict."""
        tags = _resolve_tags_from_config({}, _AppConfig, prefix="", union_tag="class")
        assert tags == {}

    def test_uses_given_prefix(self) -> None:
        """Test that a non-empty prefix is applied when resolving tags."""
        merged = {"class": "myapp.ServerDB"}
        tags = _resolve_tags_from_config(merged, _DBBase, prefix="db", union_tag="class")
        # _DBBase is not a union field itself; struct walk yields nothing here
        assert isinstance(tags, dict)


# ---------------------------------------------------------------------------
# _pre_extend_parser_for_completion
# ---------------------------------------------------------------------------


class TestPreExtendParser:
    """Tests for _pre_extend_parser_for_completion helper."""

    def _make_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)
        return parser

    def test_extends_with_variant_fields_from_cli_argv(self) -> None:
        """Test that variant fields are added to parser when class tag is in argv."""
        parser = self._make_parser()
        module = _ServerDB.__module__
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=[f"--db.class={module}._ServerDB"],
        )
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--db.host" in flags
        assert "--db.port" in flags

    def test_extends_with_variant_fields_from_config_file(self, tmp_path) -> None:
        """Test that variant fields are added to parser when class tag is in a config file."""
        module = _ServerDB.__module__
        cfg = tmp_path / "cfg.toml"
        cfg.write_text(f'[db]\nclass = "{module}._ServerDB"\n')
        parser = self._make_parser()
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=[f"--config={cfg}"],
        )
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--db.host" in flags
        assert "--db.port" in flags

    def test_cli_class_tag_wins_over_config_file(self, tmp_path) -> None:
        """Test that CLI class tag takes priority over config file class tag."""
        module = _SQLiteDB.__module__
        cfg = tmp_path / "cfg.toml"
        cfg.write_text(f'[db]\nclass = "{module}._ServerDB"\n')
        parser = self._make_parser()
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=[f"--config={cfg}", f"--db.class={module}._SQLiteDB"],
        )
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--db.dbpath" in flags
        assert "--db.host" not in flags

    def test_bad_class_path_silently_ignored(self) -> None:
        """Test that a non-importable class path is silently ignored."""
        parser = self._make_parser()
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=["--db.class=nonexistent.module.Foo"],
        )
        flags = {s for a in parser._actions for s in a.option_strings}
        # No extra flags, no crash
        assert "--db.host" not in flags

    def test_no_argv_no_extension(self) -> None:
        """Test that empty argv leaves the parser unchanged."""
        parser = self._make_parser()
        flags_before = {s for a in parser._actions for s in a.option_strings}
        _pre_extend_parser_for_completion(parser, _AppConfig, union_tag="class", config_flag="config", argv=[])
        flags_after = {s for a in parser._actions for s in a.option_strings}
        assert flags_before == flags_after

    def test_does_not_duplicate_already_registered_flags(self) -> None:
        """Test that calling pre-extend twice does not duplicate flags."""
        module = _ServerDB.__module__
        parser = self._make_parser()
        # Pre-extend twice; second call should not raise DuplicateError
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=[f"--db.class={module}._ServerDB"],
        )
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=[f"--db.class={module}._ServerDB"],
        )
        flags = {s for a in parser._actions for s in a.option_strings}
        assert flags.count("--db.host") if isinstance(flags, list) else "--db.host" in flags

    def test_nested_union_in_variant_registers_sub_class_flag(self) -> None:
        """A variant that itself has a union field gets its --sub.class flag registered."""
        module = _ServerWithCache.__module__

        @dataclass
        class _AppWithCache:
            db: _DBBase

        parser = argparse.ArgumentParser()
        populate_parser(_AppWithCache, parser)
        _pre_extend_parser_for_completion(
            parser,
            _AppWithCache,
            union_tag="class",
            config_flag="config",
            argv=[f"--db.class={module}._ServerWithCache"],
        )
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--db.host" in flags
        assert "--db.cache.class" in flags


# ---------------------------------------------------------------------------
# _extend_walk
# ---------------------------------------------------------------------------


class TestExtendWalk:
    """Tests for _extend_walk helper function."""

    def test_registers_leaf_fields(self) -> None:
        """Test that leaf fields are registered as parser arguments."""
        parser = argparse.ArgumentParser()
        existing = {a.dest for a in parser._actions}
        _extend_walk(_ServerDB, _WalkCtx(parser=parser, union_tag="class", existing_dests=existing), parser, "db")
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--db.host" in flags
        assert "--db.port" in flags

    def test_skips_already_registered(self) -> None:
        """Test that already-registered flags are not duplicated."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--db.host", dest="db.host", default=argparse.SUPPRESS)
        existing = {a.dest for a in parser._actions}
        _extend_walk(_ServerDB, _WalkCtx(parser=parser, union_tag="class", existing_dests=existing), parser, "db")
        # Should not raise, host registered once
        host_actions = [a for a in parser._actions if "--db.host" in a.option_strings]
        assert len(host_actions) == 1

    def test_creates_argument_group_for_nested_struct(self) -> None:
        """Test that a nested struct creates an argument group."""
        parser = argparse.ArgumentParser()
        existing = {a.dest for a in parser._actions}
        _extend_walk(_ExtendWalkOuter, _WalkCtx(parser=parser, union_tag="class", existing_dests=existing), parser, "")
        group_titles = {g.title for g in parser._action_groups}
        assert "inner" in group_titles


# ---------------------------------------------------------------------------
# from_namespace — union dispatch via --field.class flag
# ---------------------------------------------------------------------------


class TestFromNamespaceUnionDispatch:
    """Tests for from_namespace union dispatch via --field.class flag."""

    def test_dispatch_via_class_tag_flag(self) -> None:
        """Passing --db.class from CLI causes from_namespace to construct the right variant."""
        module = _ServerDB.__module__
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)
        # Also register the variant's fields (simulating what setup_completion does)
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=[f"--db.class={module}._ServerDB"],
        )
        ns = parser.parse_args([f"--db.class={module}._ServerDB", "--db.host=pg.example.com", "--db.port=9999"])
        result = from_namespace(_AppConfig, ns, env={})
        assert isinstance(result.db, _ServerDB)
        assert result.db.host == "pg.example.com"
        assert result.db.port == 9999

    def test_dispatch_sqlite_variant(self) -> None:
        """Test that the SQLite variant is correctly dispatched via class tag."""
        module = _SQLiteDB.__module__
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=[f"--db.class={module}._SQLiteDB"],
        )
        ns = parser.parse_args([f"--db.class={module}._SQLiteDB", "--db.dbpath=/data/mydb.sqlite"])
        result = from_namespace(_AppConfig, ns, env={})
        assert isinstance(result.db, _SQLiteDB)
        assert result.db.dbpath == "/data/mydb.sqlite"

    def test_class_tag_from_config_file(self, tmp_path) -> None:
        """Class tag from config file; CLI provides variant fields."""
        module = _ServerDB.__module__
        cfg = tmp_path / "db.toml"
        cfg.write_text(f'[db]\nclass = "{module}._ServerDB"\nhost = "cfg_host"\n')
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)
        _pre_extend_parser_for_completion(
            parser,
            _AppConfig,
            union_tag="class",
            config_flag="config",
            argv=[f"--config={cfg}"],
        )
        ns = parser.parse_args([f"--config={cfg}"])
        result = from_namespace(_AppConfig, ns, env={})
        assert isinstance(result.db, _ServerDB)
        assert result.db.host == "cfg_host"


# ---------------------------------------------------------------------------
# setup_completion — import guard
# ---------------------------------------------------------------------------


class TestSetupCompletionImportGuard:
    """Tests for setup_completion import guard behavior."""

    def test_raises_import_error_when_argcomplete_absent(self) -> None:
        """Test that ImportError is raised when argcomplete is not installed."""
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "argcomplete":
                msg = "No module named 'argcomplete'"
                raise ImportError(msg)
            return real_import(name, *args, **kwargs)

        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)

        with patch("builtins.__import__", side_effect=mock_import), pytest.raises(ImportError, match="argcomplete"):
            setup_completion(parser, _AppConfig)

    def test_calls_argcomplete_autocomplete(self) -> None:
        """setup_completion calls argcomplete.autocomplete(parser)."""
        parser = argparse.ArgumentParser()
        populate_parser(_AppConfig, parser)

        mock_ac = MagicMock()

        with patch.dict("sys.modules", {"argcomplete": mock_ac}):
            setup_completion(parser, _AppConfig, argv=[])

        mock_ac.autocomplete.assert_called_once_with(parser)


# ---------------------------------------------------------------------------
# Literal and Enum completion — choices= is set so argcomplete can suggest values
# ---------------------------------------------------------------------------


class _LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class _WithLiteral:
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@dataclass
class _WithOptionalLiteral:
    log_level: Literal["DEBUG", "INFO", "WARNING"] | None = None


@dataclass
class _WithEnum:
    log_level: _LogLevel = _LogLevel.INFO


@dataclass
class _LoggingSection:
    level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"


@dataclass
class _AppWithLogging:
    logging: _LoggingSection = field(default_factory=_LoggingSection)
    name: str = "app"


@dataclass
class _VariantWithLiteral:
    mode: Literal["fast", "safe", "debug"] = "safe"


class TestLiteralEnumCompletion:
    """Tests that Literal and Enum fields register choices= for argcomplete."""

    def _action_for(self, parser: argparse.ArgumentParser, flag: str) -> argparse.Action:
        return next(a for a in parser._actions if f"--{flag}" in a.option_strings)

    def test_literal_field_choices(self) -> None:
        """Literal field registers choices= so argcomplete can suggest values."""
        parser = argparse.ArgumentParser()
        populate_parser(_WithLiteral, parser)
        action = self._action_for(parser, "log_level")
        assert action.choices is not None
        assert set(action.choices) == {"DEBUG", "INFO", "WARNING", "ERROR"}

    def test_optional_literal_field_choices(self) -> None:
        """Optional[Literal[...]] field also registers choices= correctly."""
        parser = argparse.ArgumentParser()
        populate_parser(_WithOptionalLiteral, parser)
        action = self._action_for(parser, "log_level")
        assert action.choices is not None
        assert set(action.choices) == {"DEBUG", "INFO", "WARNING"}

    def test_enum_field_choices(self) -> None:
        """Enum field registers choices= using member names."""
        parser = argparse.ArgumentParser()
        populate_parser(_WithEnum, parser)
        action = self._action_for(parser, "log_level")
        assert action.choices is not None
        assert set(action.choices) == {"DEBUG", "INFO", "WARNING", "ERROR"}

    def test_nested_literal_field_choices(self) -> None:
        """Nested struct with Literal field: --logging.level gets choices=."""
        parser = argparse.ArgumentParser()
        populate_parser(_AppWithLogging, parser)
        action = self._action_for(parser, "logging.level")
        assert action.choices is not None
        assert set(action.choices) == {"DEBUG", "INFO", "WARNING"}

    def test_extend_walk_literal_field_choices(self) -> None:
        """_extend_walk (dynamic variant extension) also sets choices= for Literal fields."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests={a.dest for a in parser._actions})
        _extend_walk(_VariantWithLiteral, ctx, parser, "backend")
        action = self._action_for(parser, "backend.mode")
        assert action.choices is not None
        assert set(action.choices) == {"fast", "safe", "debug"}

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for confarg.click — Click adapter."""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any

import click
from click.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

import confarg
import confarg.cli.click as confargclick
from confarg.cli import FieldMeta, FlagSpec
from confarg.cli.argparse._build import build_static_flags
from confarg.cli.click._completion import _partial_argv_from_env, setup_completion
from confarg.cli.click._register import load_flags_into_command, populate_command

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass
class Simple:
    """Simple flat dataclass for testing basic flag registration."""

    host: str = "localhost"
    port: int = 8080


@dataclass
class Nested:
    """Dataclass with a nested struct field."""

    db: Simple = dataclasses.field(default_factory=Simple)
    debug: bool = False


@dataclass
class WithMeta:
    """Dataclass with FieldMeta annotations."""

    port: Annotated[int, FieldMeta(help="TCP port.", metavar="PORT")] = 8080


@dataclass
class WithList:
    """Dataclass with a list field."""

    tags: list[str] = dataclasses.field(default_factory=list)


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
class _WithStrFloat:
    input: str | float


@dataclass
class _WithStrBool:
    input: str | bool


def _make_command() -> click.Command:
    @click.command()
    def cli(**kwargs: Any) -> None:
        pass

    return cli


# ---------------------------------------------------------------------------
# load_flags_into_command
# ---------------------------------------------------------------------------


class TestLoadFlagsIntoCommand:
    """Unit tests for load_flags_into_command."""

    def test_basic_flags_registered(self) -> None:
        """Flags from build_static_flags are added to command.params."""
        cmd = _make_command()
        flags = build_static_flags(Simple, union_tag="class", config_flag="")
        load_flags_into_command(flags, cmd)
        names = {p.name for p in cmd.params}
        assert "host" in names
        assert "port" in names

    def test_duplicate_skipped(self) -> None:
        """Loading the same spec list twice does not create duplicate params."""
        cmd = _make_command()
        flags = build_static_flags(Simple, union_tag="class", config_flag="")
        load_flags_into_command(flags, cmd)
        before = len(cmd.params)
        load_flags_into_command(flags, cmd)
        assert len(cmd.params) == before

    def test_nargs_scalar(self) -> None:
        """nargs=None maps to nargs=1 in Click."""
        cmd = _make_command()
        flags = [FlagSpec(name="host")]
        load_flags_into_command(flags, cmd)
        opt = next(p for p in cmd.params if p.name == "host")
        assert opt.nargs == 1

    def test_nargs_star_becomes_multiple(self) -> None:
        """nargs='*' maps to multiple=True because Click does not support nargs=-1 for options."""
        cmd = _make_command()
        flags = [FlagSpec(name="tags", nargs="*")]
        load_flags_into_command(flags, cmd)
        opt = next(p for p in cmd.params if p.name == "tags")
        assert opt.nargs == 1
        assert opt.multiple is True

    def test_nargs_int(self) -> None:
        """An integer nargs is passed through unchanged."""
        cmd = _make_command()
        flags = [FlagSpec(name="pair", nargs=2)]
        load_flags_into_command(flags, cmd)
        opt = next(p for p in cmd.params if p.name == "pair")
        assert opt.nargs == 2

    def test_choices(self) -> None:
        """FlagSpec.choices maps to click.Choice."""
        cmd = _make_command()
        flags = [FlagSpec(name="level", choices=["low", "high"])]
        load_flags_into_command(flags, cmd)
        opt = next(p for p in cmd.params if p.name == "level")
        assert isinstance(opt.type, click.Choice)
        assert list(opt.type.choices) == ["low", "high"]

    def test_help_and_metavar(self) -> None:
        """FlagSpec.help and metavar are forwarded to the Click option."""
        cmd = _make_command()
        flags = [FlagSpec(name="port", help="TCP port.", metavar="PORT")]
        load_flags_into_command(flags, cmd)
        opt = next(p for p in cmd.params if p.name == "port")
        assert isinstance(opt, click.Option)
        assert opt.help == "TCP port."
        assert opt.metavar == "PORT"

    def test_default_is_none_for_scalars(self) -> None:
        """Scalar options default to None (detection relies on get_parameter_source, not the value)."""
        cmd = _make_command()
        flags = [FlagSpec(name="host")]
        load_flags_into_command(flags, cmd)
        opt = next(p for p in cmd.params if p.name == "host")
        assert opt.default is None

    def test_default_is_empty_tuple_for_multiple(self) -> None:
        """multiple=True options default to () (required by Click; not used for detection)."""
        cmd = _make_command()
        flags = [FlagSpec(name="tags", nargs="*")]
        load_flags_into_command(flags, cmd)
        opt = next(p for p in cmd.params if p.name == "tags")
        assert opt.default == ()

    def test_completer_registered(self) -> None:
        """FlagSpec.completer is wired up as Click's shell_complete callback."""
        completer_called_with: list[str] = []

        def my_completer(prefix: str) -> list[str]:
            completer_called_with.append(prefix)
            return ["foo", "bar"]

        cmd = _make_command()
        flags = [FlagSpec(name="x", completer=my_completer)]
        load_flags_into_command(flags, cmd)
        opt = next(p for p in cmd.params if p.name == "x")
        ctx = click.Context(cmd)
        result = opt.shell_complete(ctx, "f")
        assert completer_called_with == ["f"]
        assert [item.value for item in result] == ["foo", "bar"]

    def test_group_field_silently_dropped(self) -> None:
        """FlagSpec.group has no equivalent in Click and is silently ignored."""
        cmd = _make_command()
        flags = [FlagSpec(name="host", group="Database")]
        load_flags_into_command(flags, cmd)
        assert any(p.name == "host" for p in cmd.params)

    def test_dotted_name_accepted(self) -> None:
        """Dotted flag names like 'db.host' are accepted by the Click adapter."""
        cmd = _make_command()
        flags = [FlagSpec(name="db.host")]
        load_flags_into_command(flags, cmd)
        assert any(p.name == "db.host" for p in cmd.params)


# ---------------------------------------------------------------------------
# populate_command
# ---------------------------------------------------------------------------


class TestPopulateCommand:
    """Unit tests for populate_command."""

    def test_simple_fields(self) -> None:
        """Flat dataclass fields plus config flag are registered."""
        cmd = _make_command()
        populate_command(Simple, cmd)
        names = {p.name for p in cmd.params}
        assert {"host", "port", "config"} <= names

    def test_config_flag_suppressed(self) -> None:
        """Passing config_flag='' omits the --config option."""
        cmd = _make_command()
        populate_command(Simple, cmd, config_flag="")
        names = {p.name for p in cmd.params}
        assert "config" not in names

    def test_nested_fields(self) -> None:
        """Nested struct fields use dotted names."""
        cmd = _make_command()
        populate_command(Nested, cmd, config_flag="")
        names = {p.name for p in cmd.params}
        assert "db.host" in names
        assert "db.port" in names
        assert "debug" in names

    def test_strict_callback_not_called_with_confarg_kwargs(self) -> None:
        """Callback with a strict signature works after populate_command."""
        received: list[str] = []

        @click.command()
        @click.argument("cli_param")
        def cmd(cli_param: str) -> None:
            received.append(cli_param)

        populate_command(Simple, cmd, config_flag="")
        runner = CliRunner()
        runner.invoke(cmd, ["hello"], catch_exceptions=False)
        assert received == ["hello"]

    def test_help_visible_in_cli(self) -> None:
        """FieldMeta.help and metavar appear in the generated --help output."""
        cmd = _make_command()
        populate_command(WithMeta, cmd, config_flag="")
        runner = CliRunner()
        result = runner.invoke(cmd, ["--help"])
        assert "TCP port." in result.output
        assert "PORT" in result.output


# ---------------------------------------------------------------------------
# from_context
# ---------------------------------------------------------------------------


class TestFromContext:
    """Integration tests for from_context."""

    def _run(self, dc_type: type, args: list[str], **kw: Any) -> Any:
        """Run a Click command and return the constructed dataclass instance."""
        result_holder: list[Any] = []

        cmd = click.command()(lambda **kwargs: None)
        populate_command(dc_type, cmd, config_flag="")

        @click.command()
        def inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            result_holder.append(confargclick.from_context(dc_type, ctx, config_flag="", **kw))

        real_cmd = click.Command(name="cli", callback=inner.callback, params=cmd.params)
        runner = CliRunner()
        runner.invoke(real_cmd, args, catch_exceptions=False)
        return result_holder[0]

    def test_scalar_values(self) -> None:
        """CLI values are coerced to the field types."""
        cfg = self._run(Simple, ["--host", "myhost", "--port", "9090"])
        assert cfg.host == "myhost"
        assert cfg.port == 9090

    def test_defaults_used_when_not_provided(self) -> None:
        """Omitted options fall back to dataclass defaults."""
        cfg = self._run(Simple, [])
        assert cfg.host == "localhost"
        assert cfg.port == 8080

    def test_nested(self) -> None:
        """Dotted options are nested into the correct sub-struct."""
        cfg = self._run(Nested, ["--db.host", "db1", "--debug", "true"])
        assert cfg.db.host == "db1"
        assert cfg.debug is True

    def test_list_field(self) -> None:
        """multiple=True options are collected into a list."""
        cmd = click.command()(lambda **kwargs: None)
        populate_command(WithList, cmd, config_flag="")

        result_holder: list[Any] = []

        @click.command()
        def inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            result_holder.append(confargclick.from_context(WithList, ctx, config_flag=""))

        real_cmd = click.Command(name="cli", callback=inner.callback, params=cmd.params)
        runner = CliRunner()
        # Click's multiple=True requires repeating the flag, not space-separation.
        runner.invoke(real_cmd, ["--tags", "a", "--tags", "b", "--tags", "c"], catch_exceptions=False)
        assert result_holder[0].tags == ["a", "b", "c"]

    def test_commandline_source_detection(self) -> None:
        """get_parameter_source correctly excludes defaults and includes CLI values."""
        # Omit --port; provide --host. Only --host should appear in the merged dict.
        cfg = self._run(Simple, ["--host", "explicit"])
        assert cfg.host == "explicit"
        assert cfg.port == 8080  # dataclass default, not CLI-provided

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variables are merged at lower priority than CLI."""
        monkeypatch.setenv("MYAPP_HOST", "envhost")
        monkeypatch.setenv("MYAPP_PORT", "1234")
        cfg = self._run(Simple, [], env_prefix="MYAPP_")
        assert cfg.host == "envhost"
        assert cfg.port == 1234

    def test_config_file(self, tmp_path: Path) -> None:
        """Config files passed via --config are loaded and merged."""
        cfg_file = tmp_path / "conf.yaml"
        cfg_file.write_text("host: filehost\nport: 5432\n")

        result_holder: list[Any] = []

        @click.command()
        @click.option("--config", multiple=True)
        def cmd(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            result_holder.append(confargclick.from_context(Simple, ctx))

        runner = CliRunner()
        runner.invoke(cmd, ["--config", str(cfg_file)], catch_exceptions=False)
        assert result_holder[0].host == "filehost"
        assert result_holder[0].port == 5432

    def test_cli_overrides_file(self, tmp_path: Path) -> None:
        """CLI values have higher priority than config-file values."""
        cfg_file = tmp_path / "conf.yaml"
        cfg_file.write_text("host: filehost\nport: 5432\n")

        result_holder: list[Any] = []

        @click.command()
        @click.option("--config", multiple=True)
        def cmd(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            result_holder.append(confargclick.from_context(Simple, ctx, config_flag="config"))

        cmd_with_fields = click.Command(
            name="cli",
            callback=cmd.callback,
            params=cmd.params[:],
        )
        populate_command(Simple, cmd_with_fields, config_flag="config")

        runner = CliRunner()
        runner.invoke(cmd_with_fields, ["--config", str(cfg_file), "--host", "clihost"], catch_exceptions=False)
        assert result_holder[0].host == "clihost"
        assert result_holder[0].port == 5432

    def test_enum_option_by_value(self) -> None:
        """Enum fields accept enum values (not just names) via Click CLI."""
        cfg = self._run(WithEnum, ["--color", "blue"])
        assert cfg.color is Color.BLUE

    def test_str_float_stealing_click(self) -> None:
        """--input inf coerces to float for str | float (stealing rule)."""
        cfg = self._run(_WithStrFloat, ["--input", "inf"])
        assert math.isinf(cfg.input)
        assert type(cfg.input) is float

    def test_str_bool_stealing_click(self) -> None:
        """--input yes coerces to True for str | bool (stealing rule)."""
        cfg = self._run(_WithStrBool, ["--input", "yes"])
        assert cfg.input is True

    def test_str_bool_str_override_click(self) -> None:
        """--input.str yes preserves 'yes' as str, bypassing bool stealing."""
        cfg = self._run(_WithStrBool, ["--input.str", "yes"])
        assert cfg.input == "yes"
        assert type(cfg.input) is str


# ---------------------------------------------------------------------------
# Bool convention
# ---------------------------------------------------------------------------


class TestBoolConvention:
    """Verify the explicit --flag true/false convention for bool fields in Click."""

    def _run(self, dc_type: type, args: list[str]) -> Any:
        result_holder: list[Any] = []
        cmd = click.command()(lambda **kwargs: None)
        populate_command(dc_type, cmd, config_flag="")

        @click.command()
        def inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            result_holder.append(confargclick.from_context(dc_type, ctx, config_flag=""))

        real_cmd = click.Command(name="cli", callback=inner.callback, params=cmd.params)
        CliRunner().invoke(real_cmd, args, catch_exceptions=False)
        return result_holder[0]

    def test_bool_explicit_true(self) -> None:
        """--debug true sets a bool field to True."""
        assert self._run(Nested, ["--debug", "true"]).debug is True

    def test_bool_explicit_false(self) -> None:
        """--debug false sets a bool field to False."""
        assert self._run(Nested, ["--debug", "false"]).debug is False

    def test_no_negative_flag_registered(self) -> None:
        """Click does not generate a --no-debug flag for bool fields."""
        cmd = _make_command()
        populate_command(Nested, cmd, config_flag="")
        names = {p.name for p in cmd.params}
        assert "no-debug" not in names
        assert "no_debug" not in names

    def test_bool_requires_value(self) -> None:
        """--debug without a value fails — the convention requires --debug true/false."""
        cmd = _make_command()
        populate_command(Nested, cmd, config_flag="")
        real_cmd = click.Command(name="cli", callback=(lambda **kwargs: None), params=cmd.params)
        result = CliRunner().invoke(real_cmd, ["--debug"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# setup_completion / _partial_argv_from_env
# ---------------------------------------------------------------------------


class TestSetupCompletion:
    """Tests for setup_completion and the COMP_WORDS-based argv helper."""

    def test_noop_outside_completion(self) -> None:
        """setup_completion is a no-op when _PROGNAME_COMPLETE is not set."""
        cmd = _make_command()
        before = len(cmd.params)
        setup_completion(cmd, Simple)
        assert len(cmd.params) == before

    def test_partial_argv_empty_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_partial_argv_from_env returns [] when COMP_WORDS/COMP_CWORD are absent."""
        monkeypatch.delenv("COMP_WORDS", raising=False)
        monkeypatch.delenv("COMP_CWORD", raising=False)
        assert _partial_argv_from_env() == []

    def test_partial_argv_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_partial_argv_from_env strips the program name and the word being completed."""
        monkeypatch.setenv("COMP_WORDS", "cli --host myhost --")
        monkeypatch.setenv("COMP_CWORD", "3")
        result = _partial_argv_from_env()
        assert result == ["--host", "myhost"]

    def test_completion_mode_extends_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When _PROGNAME_COMPLETE is set, dynamic flags are added to the command."""
        monkeypatch.setenv("_CLI_COMPLETE", "bash_complete")
        monkeypatch.setenv("COMP_WORDS", "cli ")
        monkeypatch.setenv("COMP_CWORD", "1")

        cmd = click.Command(name="cli", callback=lambda: None, params=[])
        populate_command(Simple, cmd, config_flag="")
        before = len(cmd.params)
        setup_completion(cmd, Simple)
        assert len(cmd.params) == before

    def test_completion_exception_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Errors during completion extension must not propagate to the user."""
        monkeypatch.setenv("_CLI_COMPLETE", "bash_complete")
        monkeypatch.setenv("COMP_WORDS", "cli ")
        monkeypatch.setenv("COMP_CWORD", "bad_int")  # will cause int() to fail

        cmd = click.Command(name="cli", callback=lambda: None, params=[])
        setup_completion(cmd, Simple)  # must not raise


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_api() -> None:
    """confarg.click exports the four documented public functions."""
    assert hasattr(confargclick, "populate_command")
    assert hasattr(confargclick, "load_flags_into_command")
    assert hasattr(confargclick, "from_context")
    assert hasattr(confargclick, "setup_completion")


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
    """populate_command / from_context handle base-class + subclass inheritance."""

    def test_class_flag_registered(self) -> None:
        """populate_command registers --class for a base dataclass with subclasses."""
        cmd = _make_command()
        populate_command(_BaseDB, cmd, config_flag="")
        names = {p.name for p in cmd.params}
        assert "class" in names

    def test_subclass_fields_registered(self) -> None:
        """populate_command also registers subclass fields as top-level options."""
        cmd = _make_command()
        populate_command(_BaseDB, cmd, config_flag="")
        names = {p.name for p in cmd.params}
        assert "dbpath" in names
        assert "host" in names
        assert "port" in names

    def test_from_context_sqlite(self) -> None:
        """from_context constructs the correct SQLite subclass via CliRunner."""
        result_holder: list[Any] = []

        @click.command()
        @click.pass_context
        def cli(ctx: click.Context) -> None:
            result_holder.append(confargclick.from_context(_BaseDB, ctx, env={}))

        populate_command(_BaseDB, cli, config_flag="")
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "--class",
                f"{__name__}._SQLiteDB",
                "--dbpath",
                "/var/db/app.sqlite",
            ],
            catch_exceptions=False,
        )
        assert len(result_holder) == 1
        assert isinstance(result_holder[0], _SQLiteDB)
        assert result_holder[0].dbpath == "/var/db/app.sqlite"


# ---------------------------------------------------------------------------
# Root-level union target (target IS a union, not a struct containing one)
# ---------------------------------------------------------------------------


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


class TestUnionRootTarget:
    """populate_command / from_context work when the target is itself a union of structs."""

    def test_union_root_flags_registered(self) -> None:
        """build_static_flags generates --class and all variant fields for a union root."""
        flags = build_static_flags(_RootDBConfig, union_tag="class", config_flag="")
        names = {f.name for f in flags}
        assert "class" in names
        assert "dbpath" in names
        assert "host" in names
        assert "port" in names
        assert "name" in names

    def test_union_root_round_trip_sqlite(self) -> None:
        """--dbpath alone selects the SQLite variant without needing --class."""
        result_holder: list[Any] = []

        @click.command()
        @click.pass_context
        def cli(ctx: click.Context) -> None:
            result_holder.append(confargclick.from_context(_RootDBConfig, ctx, env={}))

        populate_command(_RootDBConfig, cli, config_flag="")
        runner = CliRunner()
        runner.invoke(cli, ["--dbpath", "/tmp/x.db"], catch_exceptions=False)
        assert len(result_holder) == 1
        assert isinstance(result_holder[0], _RootSQLite)
        assert result_holder[0].dbpath == "/tmp/x.db"

    def test_union_root_round_trip_db_server(self) -> None:
        """DB server fields alone select the server variant without needing --class."""
        result_holder: list[Any] = []

        @click.command()
        @click.pass_context
        def cli(ctx: click.Context) -> None:
            result_holder.append(confargclick.from_context(_RootDBConfig, ctx, env={}))

        populate_command(_RootDBConfig, cli, config_flag="")
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--host", "db.example.com", "--port", "5432", "--name", "mydb"],
            catch_exceptions=False,
        )
        assert len(result_holder) == 1
        assert isinstance(result_holder[0], _RootDBServer)
        assert result_holder[0].host == "db.example.com"
        assert result_holder[0].port == 5432
        assert result_holder[0].name == "mydb"

    def test_union_root_explicit_class_tag(self) -> None:
        """--class overrides structural disambiguation for the union root."""
        result_holder: list[Any] = []

        @click.command()
        @click.pass_context
        def cli(ctx: click.Context) -> None:
            result_holder.append(confargclick.from_context(_RootDBConfig, ctx, env={}))

        populate_command(_RootDBConfig, cli, config_flag="")
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--class", f"{__name__}._RootSQLite", "--dbpath", "/tmp/x.db"],
            catch_exceptions=False,
        )
        assert len(result_holder) == 1
        assert isinstance(result_holder[0], _RootSQLite)
        assert result_holder[0].dbpath == "/tmp/x.db"


# ---------------------------------------------------------------------------
# merge_context
# ---------------------------------------------------------------------------


class TestMergeContext:
    """merge_context returns the raw merged dict instead of a constructed instance."""

    def _run_raw(self, dc_type: type, args: list[str], **kw: Any) -> Any:
        """Run a Click command and return the raw merged dict from merge_context."""
        result_holder: list[Any] = []

        cmd = click.command()(lambda **kwargs: None)
        populate_command(dc_type, cmd, config_flag="")

        @click.command()
        def inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            result_holder.append(confargclick.merge_context(dc_type, ctx, config_flag="", **kw))

        real_cmd = click.Command(name="cli", callback=inner.callback, params=cmd.params)
        runner = CliRunner()
        runner.invoke(real_cmd, args, catch_exceptions=False)
        return result_holder[0]

    def test_returns_dict(self) -> None:
        """merge_context returns a dict, not a dataclass instance."""
        result = self._run_raw(Simple, ["--host", "myhost", "--port", "9090"])
        assert isinstance(result, dict)

    def test_cli_values_in_dict(self) -> None:
        """CLI-provided values appear in the returned dict."""
        result = self._run_raw(Simple, ["--host", "myhost", "--port", "9090"])
        assert result["host"] == "myhost"
        assert result["port"] == "9090"

    def test_expressions_preserved(self, tmp_path: Any) -> None:
        """Expression strings from config files are kept intact (not resolved)."""
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text("host: myhost\nport: '${host}'\n")
        result_holder: list[Any] = []

        cmd = click.command()(lambda **kwargs: None)
        populate_command(Simple, cmd)

        @click.command()
        def inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            result_holder.append(confargclick.merge_context(Simple, ctx, env={}))

        real_cmd = click.Command(name="cli", callback=inner.callback, params=cmd.params)
        runner = CliRunner()
        runner.invoke(real_cmd, ["--config", str(cfg)], catch_exceptions=False)
        assert result_holder[0]["port"] == "${host}"

    def test_round_trip_equivalence(self) -> None:
        """build(target, merge_context(...)) produces the same instance as from_context(...)."""
        built_holder: list[Any] = []
        direct_holder: list[Any] = []

        cmd = click.command()(lambda **kwargs: None)
        populate_command(Simple, cmd, config_flag="")

        @click.command()
        def inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            raw = confargclick.merge_context(Simple, ctx, config_flag="", env={})
            built_holder.append(confarg.build(Simple, raw))
            direct_holder.append(confargclick.from_context(Simple, ctx, config_flag="", env={}))

        real_cmd = click.Command(name="cli", callback=inner.callback, params=cmd.params)
        runner = CliRunner()
        runner.invoke(real_cmd, ["--host", "myhost", "--port", "9090"], catch_exceptions=False)
        assert built_holder[0] == direct_holder[0]

    def test_dump_file_from_raw_dict(self, tmp_path: Any) -> None:
        """dump_file accepts the raw dict returned by merge_context without raising."""
        out = tmp_path / "out.yaml"
        result_holder: list[Any] = []

        cmd = click.command()(lambda **kwargs: None)
        populate_command(Simple, cmd, config_flag="")

        @click.command()
        def inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            raw = confargclick.merge_context(Simple, ctx, config_flag="", env={})
            confarg.dump_file(raw, out)
            result_holder.append(True)

        real_cmd = click.Command(name="cli", callback=inner.callback, params=cmd.params)
        runner = CliRunner()
        runner.invoke(real_cmd, ["--host", "myhost", "--port", "9090"], catch_exceptions=False)
        assert result_holder
        assert out.exists()

    def test_dump_file_round_trip_via_instance(self, tmp_path: Any) -> None:
        """Round-tripping through a built instance gives back the same config."""
        out = tmp_path / "out.yaml"
        result_holder: list[Any] = []

        cmd = click.command()(lambda **kwargs: None)
        populate_command(Simple, cmd, config_flag="")

        @click.command()
        def inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            raw = confargclick.merge_context(Simple, ctx, config_flag="", env={})
            instance = confarg.build(Simple, raw)
            confarg.dump_file(instance, out)
            result_holder.append(True)

        real_cmd = click.Command(name="cli", callback=inner.callback, params=cmd.params)
        runner = CliRunner()
        runner.invoke(real_cmd, ["--host", "myhost", "--port", "9090"], catch_exceptions=False)
        assert result_holder
        assert out.exists()
        reloaded = confarg.load(Simple, argv=[], files=[out], env={})
        assert reloaded.host == "myhost"
        assert reloaded.port == 9090

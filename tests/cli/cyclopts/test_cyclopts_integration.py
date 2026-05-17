# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for confarg.cli.cyclopts — cyclopts adapter."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Literal

import cyclopts
import pytest

import confarg.cli.cyclopts as confargcyclopts
from confarg.cli import FieldMeta, FlagSpec
from confarg.cli.argparse._build import build_static_flags
from confarg.cli.cyclopts._register import _app_meta, load_flags_into_app, populate_app

if TYPE_CHECKING:
    from pathlib import Path


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


@dataclass
class WithChoices:
    """Dataclass with a Literal field."""

    level: Literal["debug", "info", "warning"] = "info"


def _make_app() -> cyclopts.App:
    return cyclopts.App()


def _option_names(args: Any) -> set[str]:
    """Return the set of all CLI option name strings from an ArgumentCollection."""
    return {str(n) for a in args for n in (a.parameter.name or ())}


def _run(dc_type: type, args: list[str], **kw: Any) -> Any:
    """Populate a fresh App, invoke from_app with *args*, return the result."""
    app = _make_app()
    populate_app(dc_type, app, config_flag="")
    return confargcyclopts.from_app(app, dc_type, argv=args, config_flag="", **kw)


# ---------------------------------------------------------------------------
# load_flags_into_app
# ---------------------------------------------------------------------------


class TestLoadFlagsIntoApp:
    """Unit tests for load_flags_into_app."""

    def test_basic_flags_registered(self) -> None:
        """Flags from build_static_flags appear in the app's argument collection."""
        app = _make_app()
        flags = build_static_flags(Simple, union_tag="class", config_flag="")
        load_flags_into_app(flags, app)
        args = app.assemble_argument_collection()
        option_names = _option_names(args)
        assert "--host" in option_names
        assert "--port" in option_names

    def test_name_map_set_on_app(self) -> None:
        """load_flags_into_app stores the name map in _app_meta."""
        app = _make_app()
        flags = build_static_flags(Simple, union_tag="class", config_flag="")
        load_flags_into_app(flags, app)
        meta = _app_meta[id(app)]
        assert meta["name_map"].get("host") == "host"
        assert meta["name_map"].get("port") == "port"

    def test_command_ref_set_on_app(self) -> None:
        """load_flags_into_app stores the synthetic command in _app_meta."""
        app = _make_app()
        flags = build_static_flags(Simple, union_tag="class", config_flag="")
        load_flags_into_app(flags, app)
        meta = _app_meta[id(app)]
        assert callable(meta["command"])

    def test_nargs_star(self) -> None:
        """nargs='*' spec produces a list-type parameter with consume_multiple."""
        app = _make_app()
        flags = [FlagSpec(name="tags", nargs="*")]
        load_flags_into_app(flags, app)
        args = app.assemble_argument_collection()
        opt = next(a for a in args if "--tags" in (str(n) for n in (a.parameter.name or ())))
        assert opt.parameter.consume_multiple is not None

    def test_nargs_int(self) -> None:
        """nargs=N spec produces a parameter with n_tokens=N."""
        app = _make_app()
        flags = [FlagSpec(name="pair", nargs=2)]
        load_flags_into_app(flags, app)
        args = app.assemble_argument_collection()
        opt = next(a for a in args if "--pair" in (str(n) for n in (a.parameter.name or ())))
        assert opt.parameter.n_tokens == 2

    def test_choices(self) -> None:
        """FlagSpec.choices maps to a Literal type hint on the parameter."""
        import typing  # noqa: PLC0415

        app = _make_app()
        flags = [FlagSpec(name="level", choices=["low", "high"])]
        load_flags_into_app(flags, app)
        args = app.assemble_argument_collection()
        opt = next(a for a in args if "--level" in (str(n) for n in (a.parameter.name or ())))
        # cyclopts resolves Optional, so hint is Literal["low", "high"] directly.
        assert typing.get_origin(opt.hint) is typing.Literal
        assert set(typing.get_args(opt.hint)) == {"low", "high"}

    def test_help_text(self) -> None:
        """FlagSpec.help is forwarded to the cyclopts Parameter."""
        app = _make_app()
        flags = [FlagSpec(name="port", help="TCP port.")]
        load_flags_into_app(flags, app)
        args = app.assemble_argument_collection()
        opt = next(a for a in args if "--port" in (str(n) for n in (a.parameter.name or ())))
        assert opt.parameter.help == "TCP port."

    def test_dotted_name(self) -> None:
        """Dotted flag names like 'db.host' use '--db.host' as the CLI name."""
        app = _make_app()
        flags = [FlagSpec(name="db.host")]
        load_flags_into_app(flags, app)
        args = app.assemble_argument_collection()
        option_names = _option_names(args)
        assert "--db.host" in option_names

    def test_group_assigned(self) -> None:
        """FlagSpec.group maps to a cyclopts Group on the parameter."""
        app = _make_app()
        flags = [FlagSpec(name="host", group="Database")]
        load_flags_into_app(flags, app)
        args = app.assemble_argument_collection()
        opt = next(a for a in args if "--host" in (str(n) for n in (a.parameter.name or ())))
        grp = opt.parameter.group
        # parameter.group is None | Group | Iterable[Group | str]; normalise to a sequence.
        grp_seq = () if grp is None else ((grp,) if hasattr(grp, "name") else grp)
        group_names = [str(g.name) if hasattr(g, "name") else str(g) for g in grp_seq]
        assert "Database" in group_names


# ---------------------------------------------------------------------------
# populate_app
# ---------------------------------------------------------------------------


class TestPopulateApp:
    """Unit tests for populate_app."""

    def test_simple_fields(self) -> None:
        """Flat dataclass fields plus config flag are registered."""
        app = _make_app()
        populate_app(Simple, app)
        args = app.assemble_argument_collection()
        option_names = _option_names(args)
        assert {"--host", "--port", "--config"} <= option_names

    def test_config_flag_suppressed(self) -> None:
        """Passing config_flag='' omits the --config option."""
        app = _make_app()
        populate_app(Simple, app, config_flag="")
        args = app.assemble_argument_collection()
        option_names = _option_names(args)
        assert "--config" not in option_names

    def test_nested_fields(self) -> None:
        """Nested struct fields use dotted option names."""
        app = _make_app()
        populate_app(Nested, app, config_flag="")
        args = app.assemble_argument_collection()
        option_names = _option_names(args)
        assert "--db.host" in option_names
        assert "--db.port" in option_names
        assert "--debug" in option_names

    def test_help_visible(self) -> None:
        """FieldMeta.help and metavar appear in the generated --help output."""
        app = _make_app()
        populate_app(WithMeta, app, config_flag="")
        from io import StringIO  # noqa: PLC0415

        from rich.console import Console  # noqa: PLC0415

        buf = StringIO()
        console = Console(file=buf, highlight=False)
        with pytest.raises(SystemExit):
            app(["--help"], console=console)
        output = buf.getvalue()
        assert "TCP port." in output
        assert "PORT" in output

    def test_choices_visible_in_help(self) -> None:
        """Choices appear in help output."""
        app = _make_app()
        populate_app(WithChoices, app, config_flag="")
        from io import StringIO  # noqa: PLC0415

        from rich.console import Console  # noqa: PLC0415

        buf = StringIO()
        console = Console(file=buf, highlight=False)
        with pytest.raises(SystemExit):
            app(["--help"], console=console)
        output = buf.getvalue()
        assert "debug" in output
        assert "info" in output
        assert "warning" in output


# ---------------------------------------------------------------------------
# from_app
# ---------------------------------------------------------------------------


class TestFromApp:
    """Integration tests for from_app."""

    def test_scalar_values(self) -> None:
        """CLI values are coerced to the field types."""
        cfg = _run(Simple, ["--host", "myhost", "--port", "9090"])
        assert cfg.host == "myhost"
        assert cfg.port == 9090

    def test_defaults_used_when_not_provided(self) -> None:
        """Omitted options fall back to dataclass defaults."""
        cfg = _run(Simple, [])
        assert cfg.host == "localhost"
        assert cfg.port == 8080

    def test_nested(self) -> None:
        """Dotted options are nested into the correct sub-struct."""
        cfg = _run(Nested, ["--db.host", "db1", "--debug", "true"])
        assert cfg.db.host == "db1"
        assert cfg.debug is True

    def test_list_field(self) -> None:
        """consume_multiple options are collected into a list."""
        cfg = _run(WithList, ["--tags", "a", "b", "c"])
        assert cfg.tags == ["a", "b", "c"]

    def test_list_field_repeated_flag(self) -> None:
        """List fields also accept repeated --flag invocations."""
        cfg = _run(WithList, ["--tags", "x", "--tags", "y"])
        assert cfg.tags == ["x", "y"]

    def test_choices_field(self) -> None:
        """Literal/choices field is accepted and coerced correctly."""
        cfg = _run(WithChoices, ["--level", "warning"])
        assert cfg.level == "warning"

    def test_only_cli_values_override_defaults(self) -> None:
        """Omitted options fall back to defaults; provided options override them."""
        cfg = _run(Simple, ["--host", "explicit"])
        assert cfg.host == "explicit"
        assert cfg.port == 8080  # dataclass default

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variables are merged at lower priority than CLI."""
        monkeypatch.setenv("MYAPP_HOST", "envhost")
        monkeypatch.setenv("MYAPP_PORT", "1234")
        cfg = _run(Simple, [], env_prefix="MYAPP_")
        assert cfg.host == "envhost"
        assert cfg.port == 1234

    def test_cli_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI values have higher priority than env vars."""
        monkeypatch.setenv("MYAPP_HOST", "envhost")
        cfg = _run(Simple, ["--host", "clihost"], env_prefix="MYAPP_")
        assert cfg.host == "clihost"

    def test_config_file(self, tmp_path: Path) -> None:
        """Config files passed via --config are loaded and merged."""
        cfg_file = tmp_path / "conf.yaml"
        cfg_file.write_text("host: filehost\nport: 5432\n")

        app = _make_app()
        populate_app(Simple, app)
        cfg = confargcyclopts.from_app(app, Simple, argv=["--config", str(cfg_file)])
        assert cfg.host == "filehost"
        assert cfg.port == 5432

    def test_cli_overrides_config_file(self, tmp_path: Path) -> None:
        """CLI values have higher priority than config-file values."""
        cfg_file = tmp_path / "conf.yaml"
        cfg_file.write_text("host: filehost\nport: 5432\n")

        app = _make_app()
        populate_app(Simple, app)
        cfg = confargcyclopts.from_app(
            app,
            Simple,
            argv=["--config", str(cfg_file), "--host", "clihost"],
        )
        assert cfg.host == "clihost"
        assert cfg.port == 5432


# ---------------------------------------------------------------------------
# Help / --help behaviour
# ---------------------------------------------------------------------------


class TestHelp:
    """Verify that --help triggers sys.exit and produces usable output."""

    def test_help_exits(self) -> None:
        """--help raises SystemExit (process would exit in real usage)."""
        app = _make_app()
        populate_app(Simple, app, config_flag="")
        with pytest.raises(SystemExit):
            app(["--help"])

    def test_help_shows_flags(self) -> None:
        """--help output contains the registered option names."""
        from io import StringIO  # noqa: PLC0415

        from rich.console import Console  # noqa: PLC0415

        app = _make_app()
        populate_app(Simple, app, config_flag="")
        buf = StringIO()
        console = Console(file=buf, highlight=False)
        with pytest.raises(SystemExit):
            app(["--help"], console=console)
        output = buf.getvalue()
        assert "--host" in output
        assert "--port" in output


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_api() -> None:
    """confarg.cli.cyclopts exports the three documented public functions."""
    assert hasattr(confargcyclopts, "populate_app")
    assert hasattr(confargcyclopts, "load_flags_into_app")
    assert hasattr(confargcyclopts, "from_app")

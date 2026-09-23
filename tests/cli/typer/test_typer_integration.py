# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for confarg.cli.typer — Typer adapter.

Behavior shared with the other front-ends is asserted once in
``tests/cli/test_backend_contract.py`` against the ``loader`` fixture.  What is left
here is typer-specific: the registration idioms, the help text, the completion hook,
and the fact that typer's vendored click fork is what the adapter registers onto
(docs-dev/architecture/04-cli-adapters.md#the-clicklike-seam).
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

import pytest
import typer
from typer._types import TyperChoice
from typer.core import TyperOption
from typer.main import get_command

import confarg.cli.typer as confargtyper
from confarg.cli import FieldMeta, FlagSpec
from confarg.cli.typer._completion import setup_completion
from confarg.cli.typer._register import load_flags_into_command, populate_command

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
class WithChoices:
    """Dataclass with a Literal field, which typer validates through TyperChoice."""

    level: Literal["debug", "info"] = "info"


@dataclass
class WithList:
    """Dataclass with a list field, registered as a repeated flag."""

    tags: list[str] = field(default_factory=list)


def _make_command(target: type | None = None, **kwargs: Any) -> Any:
    """Build a populated typer command whose callback records the loaded config."""
    app = typer.Typer(add_completion=False)

    @app.command()
    def _cli(ctx: typer.Context) -> None:
        pass

    command = get_command(app)
    if target is not None:
        populate_command(target, command, **kwargs)
    return command


def _invoke(command: Any, argv: list[str]) -> str:
    """Run a typer command, returning everything it wrote to stdout/stderr."""
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink), contextlib.suppress(SystemExit):
        command.main(args=argv, prog_name="cli", standalone_mode=True)
    return sink.getvalue()


# ---------------------------------------------------------------------------
# Registration onto typer's vendored click fork
# ---------------------------------------------------------------------------


class TestRegistration:
    """populate_command puts typer's own option class on a typer command."""

    def test_registers_dotted_options(self) -> None:
        """A nested field becomes a dotted option typer accepts."""
        command = _make_command(Nested, argv=[])
        names = {p.name for p in command.params}
        assert {"db.host", "db.port", "debug"} <= names

    def test_options_are_typer_options(self) -> None:
        """Every confarg option is a TyperOption, not a click.Option.

        A real ``click.Option`` registers fine but dies during parsing, because
        click's ``handle_parse_result`` reaches for a Context slot typer's fork does
        not have (BUG-7).
        """
        command = _make_command(Nested, argv=[])
        confarg_params = [p for p in command.params if p.name in {"db.host", "db.port", "debug"}]
        assert confarg_params
        assert all(isinstance(p, TyperOption) for p in confarg_params)

    def test_config_flag_registered(self) -> None:
        """The --config option and its subkeys are registered by default."""
        command = _make_command(Nested, argv=[])
        names = {p.name for p in command.params}
        assert "config" in names
        assert "config.db" in names

    def test_config_flag_suppressed(self) -> None:
        """config_flag="" registers no config option."""
        command = _make_command(Nested, argv=[], config_flag="")
        assert "config" not in {p.name for p in command.params}

    def test_load_flags_skips_known_names(self) -> None:
        """A spec whose name is already registered is silently skipped."""
        command = _make_command(Simple, argv=[])
        before = len(command.params)
        load_flags_into_command([FlagSpec(name="host")], command)
        assert len(command.params) == before

    def test_choices_use_an_expression_tolerant_typer_choice(self) -> None:
        """A Literal field is registered with typer's choice type, subclassed."""
        command = _make_command(WithChoices, argv=[])
        param = next(p for p in command.params if p.name == "level")
        assert isinstance(param.type, TyperChoice)

    def test_list_field_is_multiple(self) -> None:
        """A list field uses multiple=True: typer inherits click's repeated-flag syntax."""
        command = _make_command(WithList, argv=[])
        param = next(p for p in command.params if p.name == "tags")
        assert param.multiple is True

    def test_completer_uses_typers_autocompletion(self) -> None:
        """A spec with a completer is wired through autocompletion, not shell_complete.

        Typer warns and deprecates click's ``shell_complete``, so registering a
        completer that way would make every populate_command call warn.
        """
        command = _make_command()
        spec = FlagSpec(name="pick", completer=lambda prefix: [prefix + "x"])
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            load_flags_into_command([spec], command)
        param = next(p for p in command.params if p.name == "pick")
        assert param._custom_shell_complete is not None

    def test_completer_results_reach_typer(self) -> None:
        """The wrapped completer's candidates come back as typer completion items."""
        command = _make_command()
        load_flags_into_command([FlagSpec(name="pick", completer=lambda prefix: [prefix + "x"])], command)
        param = next(p for p in command.params if p.name == "pick")
        items = param._custom_shell_complete(None, param, "ab")
        assert [i.value for i in items] == ["abx"]


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------


class TestInvocation:
    """The adapter's values reach a typer command callback."""

    def test_from_context_reads_typed_options(self) -> None:
        """from_context returns a config built from what the user typed."""
        argv = ["--db.host", "db1", "--db.port", "5432"]
        seen: list[Any] = []

        app = typer.Typer(add_completion=False)

        @app.command()
        def _cli(ctx: typer.Context) -> None:
            seen.append(confargtyper.from_context(Nested, ctx, argv=argv))

        command = get_command(app)
        populate_command(Nested, command, argv=argv)
        _invoke(command, argv)

        assert seen == [Nested(db=Simple(host="db1", port=5432), debug=False)]

    def test_merge_context_returns_the_raw_dict(self) -> None:
        """merge_context returns the merged dict rather than a constructed object."""
        argv = ["--db.host", "db1"]
        seen: list[Any] = []

        app = typer.Typer(add_completion=False)

        @app.command()
        def _cli(ctx: typer.Context) -> None:
            seen.append(confargtyper.merge_context(Nested, ctx, argv=argv))

        command = get_command(app)
        populate_command(Nested, command, argv=argv)
        _invoke(command, argv)

        assert seen == [{"db": {"host": "db1"}}]

    def test_untyped_options_do_not_reach_the_merge(self) -> None:
        """A framework default is not a user-typed value, so it never overrides."""
        argv: list[str] = []
        seen: list[Any] = []

        app = typer.Typer(add_completion=False)

        @app.command()
        def _cli(ctx: typer.Context) -> None:
            seen.append(confargtyper.merge_context(Nested, ctx, argv=argv))

        command = get_command(app)
        populate_command(Nested, command, argv=argv)
        _invoke(command, argv)

        assert seen == [{}]

    def test_confarg_options_are_stripped_from_the_callback(self) -> None:
        """The command function keeps its own signature; confarg params are filtered out."""
        argv = ["--db.host", "db1"]
        called: list[bool] = []

        app = typer.Typer(add_completion=False)

        @app.command()
        def _cli(ctx: typer.Context) -> None:
            called.append(True)

        command = get_command(app)
        populate_command(Nested, command, argv=argv)
        _invoke(command, argv)

        assert called == [True]

    def test_unknown_option_is_rejected(self) -> None:
        """A flag confarg did not register is still typer's to refuse."""
        command = _make_command(Nested, argv=[])
        assert "No such option" in _invoke(command, ["--nope", "1"])


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------


class TestHelp:
    """FieldMeta reaches typer's own help rendering."""

    def test_help_and_metavar_are_shown(self) -> None:
        """FieldMeta help and metavar appear in --help."""
        command = _make_command(WithMeta, argv=[])
        out = _invoke(command, ["--help"])
        assert "TCP port." in out
        assert "PORT" in out

    def test_choices_are_shown(self) -> None:
        """A Literal field renders its declared values."""
        command = _make_command(WithChoices, argv=[])
        out = _invoke(command, ["--help"])
        assert "debug" in out
        assert "info" in out


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


class TestSetupCompletion:
    """Tests for typer's setup_completion wrapper."""

    def test_noop_outside_completion(self) -> None:
        """setup_completion is a no-op when _PROGNAME_COMPLETE is not set."""
        command = _make_command(Simple, argv=[])
        before = len(command.params)
        setup_completion(command, Simple)
        assert len(command.params) == before

    def test_completion_mode_extends_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With _PROGNAME_COMPLETE set, dynamic flags are added from COMP_WORDS."""
        command = _make_command(Simple, argv=[])
        command.name = "cli"
        monkeypatch.setenv("_CLI_COMPLETE", "bash_complete")
        monkeypatch.setenv("COMP_WORDS", "cli --port 1 --")
        monkeypatch.setenv("COMP_CWORD", "3")
        setup_completion(command, Simple)
        assert "port" in {p.name for p in command.params}

    def test_failure_degrades_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_completion swallows any exception: completion must never crash a shell."""
        command = _make_command(Simple, argv=[])
        command.name = "cli"
        monkeypatch.setenv("_CLI_COMPLETE", "bash_complete")
        monkeypatch.setattr(
            "confarg.cli._clicklike._completion.partial_argv_from_env",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        setup_completion(command, Simple)  # must not raise


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_public_names() -> None:
    """The typer adapter exports the same triple as the click one, plus completion."""
    assert set(confargtyper.__all__) == {
        "from_context",
        "load_flags_into_command",
        "merge_context",
        "populate_command",
        "setup_completion",
    }


@pytest.mark.parametrize(
    ("adapter", "absent"),
    [("confarg.cli.typer", "click"), ("confarg.cli.click", "typer")],
)
def test_neither_adapter_drags_in_the_other(adapter: str, absent: str) -> None:
    """The shared layer imports neither framework, so one adapter never pulls the other.

    Checked in a subprocess: this test session has already imported both, so only a
    fresh interpreter can answer what a single adapter costs
    (docs-dev/architecture/04-cli-adapters.md#the-clicklike-seam).
    """
    code = f"import sys, {adapter}; print({absent!r} in sys.modules)"
    out = subprocess.run(  # fixed argv, no shell, interpreter is sys.executable
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "False"

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for confarg.cli.cyclopts — cyclopts adapter."""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Callable  # noqa: TC003  # a runtime dataclass annotation
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Literal, NamedTuple, Union, get_args, get_origin
from uuid import UUID

import cyclopts
import pytest

import confarg
import confarg.cli.cyclopts as confargcyclopts
from confarg.cli import FieldMeta, FlagSpec
from confarg.cli._build import build_dynamic_flags, build_static_flags
from confarg.cli.cyclopts._register import (
    _app_meta,
    _expression_tolerant_convert,
    load_flags_into_app,
    populate_app,
)

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
    """Dataclass with a Literal field."""

    level: Literal["debug", "info", "warning"] = "info"


def _make_app() -> cyclopts.App:
    return cyclopts.App()


def _option_names(args: Any) -> set[str]:
    """Return the set of all CLI option name strings from an ArgumentCollection."""
    return {str(n) for a in args for n in (a.parameter.name or ())}


def _literal_of(hint: Any) -> Any:
    """Strip an ``Optional`` wrapper off a cyclopts ``Argument.hint``.

    cyclopts < 5 resolved ``Optional`` away when storing ``Argument.hint``; 5.0 keeps
    ``NoneType`` there so a union member can consume a different token count and parse
    ``"none"``.  ``_spec_to_inspect_param`` registers ``Literal[...] | None`` either way,
    so normalize before asserting on the Literal.
    """
    if get_origin(hint) in (Union, types.UnionType):
        rest = [a for a in get_args(hint) if a is not type(None)]
        if len(rest) == 1:
            return rest[0]
    return hint


def _run(dc_type: type, args: list[str], **kw: Any) -> Any:
    """Populate a fresh App, invoke from_app with *args*, return the result."""
    app = _make_app()
    populate_app(dc_type, app, config_flag="")
    return confargcyclopts.from_app(dc_type, app, argv=args, config_flag="", **kw)


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
        app = _make_app()
        flags = [FlagSpec(name="level", choices=["low", "high"])]
        load_flags_into_app(flags, app)
        args = app.assemble_argument_collection()
        opt = next(a for a in args if "--level" in (str(n) for n in (a.parameter.name or ())))
        # cyclopts < 5 resolves Optional away, 5.0 keeps it: see _literal_of.
        hint = _literal_of(opt.hint)
        assert get_origin(hint) is Literal
        assert set(get_args(hint)) == {"low", "high"}

    def test_choices_get_the_expression_tolerant_converter(self) -> None:
        """A choices flag carries the converter that bypasses Literal enforcement for ``${...}``."""
        app = _make_app()
        load_flags_into_app([FlagSpec(name="level", choices=["low", "high"])], app)
        args = app.assemble_argument_collection()
        opt = next(a for a in args if "--level" in (str(n) for n in (a.parameter.name or ())))
        assert opt.parameter.converter is _expression_tolerant_convert

    def test_choices_still_reject_a_plain_out_of_domain_value(self) -> None:
        """Bypassing conversion for ``${...}`` must not disable the check for ordinary values."""
        with pytest.raises(SystemExit):
            _run(WithChoices, ["--level", "nope"])

    def test_choices_admit_an_unresolved_expression(self) -> None:
        """A ``${...}`` token survives the cyclopts parse and reaches the merged dict intact."""
        app = _make_app()
        populate_app(WithChoices, app, config_flag="")
        merged = confargcyclopts.merge_app(WithChoices, app, argv=["--level", "${other}"], config_flag="", env={})
        assert merged["level"] == "${other}"

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
# Bool convention
# ---------------------------------------------------------------------------


class TestBoolConvention:
    """Verify the explicit --flag true/false convention for bool fields in cyclopts."""

    def test_bool_requires_value(self) -> None:
        """--debug without a value fails — the convention requires --debug true/false."""
        with pytest.raises(SystemExit):
            _run(Nested, ["--debug"])


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
# Index spellings are accepted but hidden from --help
# ---------------------------------------------------------------------------


class _HelpPoint(NamedTuple):
    """Namedtuple whose index spellings stay out of --help (BUG-80)."""

    x: int = 0
    y: int = 0


@dataclass
class _WithHelpPoint:
    pt: _HelpPoint = dataclasses.field(default_factory=_HelpPoint)


@dataclass
class _WithHelpPair:
    pair: tuple[str, str] = ("left", "right")


class TestHelpHidesIndexSpellings:
    """Index spellings patch a position; --help advertises the name spellings (BUG-80)."""

    @staticmethod
    def _help_output(target: type, argv: list[str]) -> str:
        from io import StringIO  # noqa: PLC0415

        from rich.console import Console  # noqa: PLC0415

        app = _make_app()
        populate_app(target, app, config_flag="", argv=argv)
        buf = StringIO()
        console = Console(file=buf, highlight=False)
        with pytest.raises(SystemExit):
            app(["--help"], console=console)
        return buf.getvalue()

    def test_namedtuple_index_flags_hidden(self) -> None:
        """A namedtuple's per-index flags are accepted but absent from --help."""
        output = self._help_output(_WithHelpPoint, [])
        assert "--pt.x" in output
        assert "--pt.0" not in output
        assert "--pt.-1" not in output

    def test_tuple_element_flag_hidden_when_typed(self) -> None:
        """A fixed tuple's element flag, registered from argv, is kept out of --help."""
        output = self._help_output(_WithHelpPair, ["--pair.0", "a"])
        assert "--pair.0" not in output


# ---------------------------------------------------------------------------
# confarg's help strings read the same under every cyclopts help format
# ---------------------------------------------------------------------------


@dataclass
class _VariantA:
    x: int = 0


@dataclass
class _VariantB:
    y: int = 0


@dataclass
class _WithHelpStrings:
    pet: _VariantA | _VariantB = dataclasses.field(default_factory=_VariantA)
    fn: Callable[[], int] | None = None
    uid: UUID = dataclasses.field(default_factory=lambda: UUID(int=0))


class TestHelpReadsUnderEveryFormat:
    """The help confarg writes is plain text that every ``help_format`` prints as written (BUG-226)."""

    _ARGV: ClassVar[list[str]] = ["--uid.class", "uuid.UUID", "--uid.hex", "0" * 32]

    @pytest.mark.parametrize("help_format", ["markdown", "restructuredtext", "rich", "plaintext"])
    @pytest.mark.usefixtures("leaf_registry")
    def test_every_confarg_help_string_survives(
        self,
        help_format: Literal["markdown", "restructuredtext", "rich", "plaintext"],
    ) -> None:
        """No placeholder, dunder or other markup in confarg's own help is eaten by the renderer."""
        from io import StringIO  # noqa: PLC0415

        from rich.console import Console  # noqa: PLC0415

        confarg.register_leaf_type(UUID, UUID)
        app = cyclopts.App(help_format=help_format)
        populate_app(_WithHelpStrings, app, argv=self._ARGV)
        buf = StringIO()
        with pytest.raises(SystemExit):
            app(["--help"], console=Console(file=buf, width=400, highlight=False))
        text = " ".join(" ".join(line.strip("│ ") for line in buf.getvalue().splitlines()).split())
        shown: dict[str, FlagSpec] = {}
        for spec in build_static_flags(_WithHelpStrings, argv=self._ARGV) + build_dynamic_flags(
            _WithHelpStrings,
            self._ARGV,
        ):
            shown.setdefault(spec.name, spec)  # the first spec of a name is the one registered
        helps = {" ".join(spec.help.split()) for spec in shown.values() if spec.help and not spec.hidden}
        assert [h for h in sorted(helps) if h not in text] == []
        # The strings checked above hold the placeholders, so the check is not vacuous.
        words = {word for help_text in helps for word in help_text.split()}
        assert {"--pet.FIELD", "--config.FIELD", "--FLAG.PARAM"} <= words


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_api() -> None:
    """confarg.cli.cyclopts exports exactly the four documented public functions."""
    assert set(confargcyclopts.__all__) == {
        "from_app",
        "load_flags_into_app",
        "merge_app",
        "populate_app",
    }
    for name in confargcyclopts.__all__:
        assert hasattr(confargcyclopts, name)


# ---------------------------------------------------------------------------
# cli_prefix (cyclopts-specific: recovery via the adapter's own _app_meta entry)
# ---------------------------------------------------------------------------


class TestCliPrefixCyclopts:
    """The prefix registered by populate_app reaches from_app on its own."""

    @staticmethod
    def _app(argv: list[str]) -> cyclopts.App:
        app = cyclopts.App()
        populate_app(Simple, app, cli_prefix="app", config_flag="", argv=argv)
        return app

    def test_prefix_recovered_from_app(self) -> None:
        """from_app needs no cli_prefix of its own."""
        argv = ["--app.host", "h"]
        result = confargcyclopts.from_app(Simple, self._app(argv), argv=argv, env={}, config_flag="")
        assert result.host == "h"

    def test_matching_prefix_accepted(self) -> None:
        """Repeating the registered prefix is allowed."""
        argv = ["--app.host", "h"]
        result = confargcyclopts.from_app(
            Simple,
            self._app(argv),
            argv=argv,
            env={},
            cli_prefix="app",
            config_flag="",
        )
        assert result.host == "h"

    def test_mismatched_prefix_raises(self) -> None:
        """A prefix disagreeing with the registered one fails loudly, not silently."""
        argv = ["--app.host", "h"]
        with pytest.raises(confarg.exceptions.ConfargError, match="cli_prefix mismatch"):
            confargcyclopts.from_app(
                Simple,
                self._app(argv),
                argv=argv,
                env={},
                cli_prefix="cfg",
                config_flag="",
            )

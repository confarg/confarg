# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Typer-specific flag loading: load_flags_into_command and populate_command."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from typer._types import TyperChoice
from typer.core import TyperOption

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from typer._click import Command, Context

    from confarg.cli._spec import FlagSpec

from confarg import _defaults
from confarg.cli import _clicklike


class _ExpressionTolerantChoice(_clicklike.ExpressionTolerantChoiceMixin, TyperChoice):
    """A ``TyperChoice`` that also admits unresolved ``${...}`` tokens."""


class _ConfargOption(_clicklike.DottedNameMixin, TyperOption):
    """TyperOption subclass that allows dotted names (not valid Python identifiers)."""


def _completer_kwargs(completer: Callable[[str], list[str]]) -> dict[str, Any]:
    """Wrap a confarg completer as typer's ``autocompletion`` callback.

    Typer deprecates click's ``shell_complete`` in favour of ``autocompletion``,
    which returns bare strings and is wrapped into completion items by typer itself.
    Typer also filters the result by ``startswith(incomplete)``, which is a no-op —
    a confarg completer already prefix-filters.
    """

    def _autocompletion(_ctx: Context, _args: list[str], incomplete: str) -> list[str]:
        return completer(incomplete)

    return {"autocompletion": _autocompletion}


def _spec_to_option(spec: FlagSpec) -> TyperOption:
    """Convert one FlagSpec to a TyperOption."""
    return _ConfargOption(
        confarg_name=spec.name,
        **_clicklike.option_kwargs(
            spec,
            choice_cls=_ExpressionTolerantChoice,
            completer_kwargs=_completer_kwargs,
        ),
    )


def load_flags_into_command(
    flags: list[FlagSpec],
    command: Command,
) -> None:
    """Load a list of :class:`~confarg.cli.FlagSpec` objects into a Typer command.

    Each spec becomes a :class:`typer.core.TyperOption` appended to
    ``command.params``.  Flags whose ``name`` is already registered are silently
    skipped.  The ``group`` field of :class:`~confarg.cli.FlagSpec` is not used —
    Typer has no argument-group concept.

    Args:
        flags: The specs to register, typically from :func:`~confarg.cli.build_static_flags`
            or :func:`~confarg.cli.build_dynamic_flags`.
        command: The command from :func:`typer.main.get_command` to populate.
    """
    _clicklike.load_flags_into_command(flags, command, _spec_to_option)


def populate_command(  # noqa: PLR0913  # mirrors populate_parser/populate_app signatures; all params are keyword-only with sensible defaults
    target: object,
    command: Command,
    *,
    cli_prefix: str = "",
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
    config_subkeys: bool = True,
    argv: Sequence[str] | None = None,
) -> None:
    """Register fields of a dataclass type as options on a Typer command.

    Mirrors :func:`~confarg.cli.click.populate_command` for Typer.  Typer builds its
    commands from a function signature, so pass the command that
    :func:`typer.main.get_command` returns for your :class:`typer.Typer` app rather
    than the app itself, and invoke that command::

        app = typer.Typer()

        @app.command()
        def main(ctx: typer.Context) -> None:
            print(from_context(Config, ctx))

        command = typer.main.get_command(app)
        populate_command(Config, command)
        command()

    The command function must take a :class:`typer.Context` parameter, which is how
    :func:`from_context` reaches the parsed options.

    A ``--<config_flag>`` option (default ``--config``) accepting multiple file
    paths is also registered.  Pass ``config_flag=""`` to suppress it.

    Args:
        target: The dataclass type whose fields to register.
        command: The command from :func:`typer.main.get_command` to populate.
        cli_prefix: Namespace every confarg option lives under, so
            ``--<prefix>.<field>`` stays distinguishable from the host
            application's own options.  Defaults to ``""`` (no prefix).  The value
            is recorded against the command, so :func:`merge_context` /
            :func:`from_context` recover it and need not repeat it.  A non-struct
            (scalar) target is registered as the bare ``--<prefix>`` option and has
            no CLI spelling without a prefix.
        union_tag: Name of the union discriminator field to skip.
        config_flag: Name of the config-file option (default ``"config"``).
            Set to ``""`` to disable config-file option registration.
        config_subkeys: Whether to register ``--<config_flag>.<field>`` options for
            each direct struct field of the root dataclass (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` option.
        argv: CLI argument list scanned to register argv-derived dynamic
            options: ``--<field>.bind.*`` for resolved ``--<field>.fn`` /
            ``--<field>.class`` callables, ``--<config_flag>.<subpath>[+]``
            scoped/append config files, and list-index / append / delete /
            dict-subkey patch options.  Defaults to ``sys.argv[1:]`` (matching
            :func:`from_context`); pass an explicit list, or ``[]`` to register
            only the static, type-derived options.
    """
    _clicklike.populate_command(
        target,
        command,
        _spec_to_option,
        _ConfargOption,
        cli_prefix=cli_prefix,
        union_tag=union_tag,
        config_flag=config_flag,
        config_subkeys=config_subkeys,
        argv=sys.argv[1:] if argv is None else argv,
    )

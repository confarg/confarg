# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Click-specific flag loading: load_flags_into_command and populate_command."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import click
from click.shell_completion import CompletionItem

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from confarg.cli._spec import FlagSpec

from confarg import _defaults
from confarg.cli import _clicklike


class _ExpressionTolerantChoice(_clicklike.ExpressionTolerantChoiceMixin, click.Choice):
    """A ``click.Choice`` that also admits unresolved ``${...}`` tokens."""


class _ConfargOption(_clicklike.DottedNameMixin, _clicklike.StandsBareMixin, click.Option):
    """click.Option subclass taking a dotted name, and a flag that may stand bare."""


def _completer_kwargs(completer: Callable[[str], list[str]]) -> dict[str, Any]:
    """Wrap a confarg completer as click's ``shell_complete`` callback."""

    def _shell_complete(
        _ctx: click.Context,
        _param: click.Parameter,
        incomplete: str,
    ) -> list[CompletionItem]:
        return [CompletionItem(v) for v in completer(incomplete)]

    return {"shell_complete": _shell_complete}


def _spec_to_option(spec: FlagSpec) -> click.Option:
    """Convert one FlagSpec to a click.Option."""
    return _ConfargOption(
        confarg_name=spec.name,
        stands_bare=spec.stands_bare,
        **_clicklike.option_kwargs(
            spec,
            choice_cls=_ExpressionTolerantChoice,
            completer_kwargs=_completer_kwargs,
        ),
    )


def load_flags_into_command(
    flags: list[FlagSpec],
    command: click.Command,
) -> None:
    """Load a list of :class:`~confarg.cli.FlagSpec` objects into a Click command.

    Each spec becomes a :class:`click.Option` appended to ``command.params``.
    Flags whose ``name`` is already registered are silently skipped.
    The ``group`` field of :class:`~confarg.cli.FlagSpec` is not used —
    Click has no argument-group concept.

    Args:
        flags: The specs to register, typically from :func:`~confarg.cli.build_static_flags`
            or :func:`~confarg.cli.build_dynamic_flags`.
        command: The :class:`click.Command` to populate.
    """
    _clicklike.load_flags_into_command(flags, command, _spec_to_option)


def populate_command(  # noqa: PLR0913  # mirrors populate_parser/populate_app signatures; all params are keyword-only with sensible defaults
    target: object,
    command: click.Command,
    *,
    cli_prefix: str = "",
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
    config_subkeys: bool = True,
    argv: Sequence[str] | None = None,
) -> None:
    """Register fields of a dataclass type as options on a Click command.

    Mirrors :func:`~confarg.cli.argparse.populate_parser` for the Click framework.
    All registered options use a sentinel default so that unprovided options are
    excluded when building the merged dict in :func:`from_context`.

    A ``--<config_flag>`` option (default ``--config``) accepting multiple file
    paths is also registered.  Pass ``config_flag=""`` to suppress it.

    Args:
        target: The dataclass type whose fields to register.
        command: The :class:`click.Command` to populate.
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

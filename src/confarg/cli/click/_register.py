# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Click-specific flag loading: load_flags_into_command and populate_command."""

from __future__ import annotations

import functools
import sys
from typing import TYPE_CHECKING, Any

import click
from click.shell_completion import CompletionItem

if TYPE_CHECKING:
    from collections.abc import Sequence

    from confarg.cli.argparse._spec import FlagSpec

from confarg import _defaults
from confarg.cli.argparse._build import build_dynamic_flags, build_static_flags
from confarg.dictexpr import contains_expression


class _ExpressionTolerantChoice(click.Choice):
    """A ``click.Choice`` that also admits unresolved ``${...}`` tokens.

    ``Choice.convert`` resolves the value through a normalized mapping, so the
    bypass has to sit in ``convert`` rather than in the choices container.
    Everything else is inherited: ``--help`` still renders ``[a|b]``, shell
    completion still offers the declared values, and a real out-of-domain value
    still fails with click's own ``'zz' is not one of 'a', 'b'.``

    An expression's value is unknown until ``resolve_expressions`` runs, so the
    front-end cannot prove it wrong at parse time; ``build()`` validates the
    resolved result instead.  Deferral goes through the canonical
    :func:`~confarg.dictexpr.contains_expression`, the same predicate the
    argparse and cyclopts adapters use.
    """

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> Any:
        """Pass an expression token through untouched; validate anything else normally."""
        if contains_expression(value):
            return value
        return super().convert(value, param, ctx)


class _ConfargOption(click.Option):
    """click.Option subclass that allows dotted names (not valid Python identifiers)."""

    def __init__(self, confarg_name: str, **kwargs: Any) -> None:
        self._confarg_name = confarg_name
        super().__init__(**kwargs)

    def _parse_decls(self, decls: Any, expose_value: bool) -> tuple[str, list[str], list[str]]:  # noqa: ARG002, FBT001  # name/type must match parent for keyword-safe override
        opts = [d for d in decls if d.startswith("-")]
        return self._confarg_name, opts, []


def _spec_to_option(spec: FlagSpec) -> click.Option:
    """Convert one FlagSpec to a click.Option."""
    if spec.nargs == 0:
        # Value-less flag (e.g. a list/dict delete --field.N-): a boolean switch.
        return _ConfargOption(
            confarg_name=spec.name,
            param_decls=[f"--{spec.name}"],
            is_flag=True,
            default=False,
            required=False,
            help=spec.help or None,
            allow_from_autoenv=False,
        )

    # Click does not support nargs=-1 for options; use multiple=True instead.
    multiple = spec.nargs == "*"
    nargs: int = 1 if (spec.nargs is None or spec.nargs == "*") else int(spec.nargs)

    type_: Any = _ExpressionTolerantChoice(spec.choices) if spec.choices else str

    default: Any = () if multiple else None

    kwargs: dict[str, Any] = {
        "param_decls": [f"--{spec.name}"],
        "type": type_,
        "nargs": nargs,
        "multiple": multiple,
        "default": default,
        "required": False,
        "help": spec.help or None,
        "metavar": spec.metavar,
        # confarg handles env vars itself via _parse_env; prevent Click from also
        # reading them via Context.auto_envvar_prefix.
        "allow_from_autoenv": False,
    }

    if spec.completer is not None:
        _fn = spec.completer

        def _shell_complete(
            _ctx: click.Context,
            _param: click.Parameter,
            incomplete: str,
        ) -> list[CompletionItem]:
            return [CompletionItem(v) for v in _fn(incomplete)]

        kwargs["shell_complete"] = _shell_complete

    return _ConfargOption(confarg_name=spec.name, **kwargs)


def load_flags_into_command(
    flags: list[FlagSpec],
    command: click.Command,
) -> None:
    """Load a list of :class:`~confarg.cli.argparse.FlagSpec` objects into a Click command.

    Each spec becomes a :class:`click.Option` appended to ``command.params``.
    Flags whose ``name`` is already registered are silently skipped.
    The ``group`` field of :class:`~confarg.cli.argparse.FlagSpec` is not used —
    Click has no argument-group concept.

    Args:
        flags: The specs to register, typically from :func:`~confarg.cli.argparse.build_static_flags`
            or :func:`~confarg.cli.argparse.build_dynamic_flags`.
        command: The :class:`click.Command` to populate.
    """
    existing = {p.name for p in command.params}
    for spec in flags:
        if spec.name in existing:
            continue
        command.params.append(_spec_to_option(spec))
        existing.add(spec.name)


def populate_command(  # noqa: PLR0913  # mirrors populate_parser/populate_app signatures; all params are keyword-only with sensible defaults
    target: object,
    command: click.Command,
    *,
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
    if argv is None:
        argv = sys.argv[1:]
    before_names = {p.name for p in command.params}

    static = build_static_flags(target, union_tag=union_tag, config_flag=config_flag, config_subkeys=config_subkeys)
    load_flags_into_command(static, command)
    dynamic = build_dynamic_flags(target, argv, union_tag=union_tag, config_flag=config_flag)
    load_flags_into_command(dynamic, command)

    confarg_names = {p.name for p in command.params} - before_names
    if command.callback is not None and confarg_names:
        _original = command.callback

        @functools.wraps(_original)
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            filtered = {k: v for k, v in kwargs.items() if k not in confarg_names}
            return _original(*args, **filtered)

        command.callback = _wrapped

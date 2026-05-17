# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Click-specific flag loading: load_flags_into_command and populate_command."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    import click

    from confarg.cli.argparse._spec import FlagSpec

from confarg import _defaults
from confarg.cli.argparse._build import build_dynamic_flags, build_static_flags


def _make_option_cls() -> type:
    """Return a click.Option subclass that allows dotted names (not valid Python identifiers)."""
    try:
        import click as _click
    except ImportError as exc:  # pragma: no cover
        msg = "click is required for confarg.cli.click: pip install confarg[click]"
        raise ImportError(msg) from exc

    class _ConfargOption(_click.Option):
        def __init__(self, confarg_name: str, **kwargs: Any) -> None:
            self._confarg_name = confarg_name
            super().__init__(**kwargs)

        def _parse_decls(self, decls: Any, expose_value: Any) -> tuple[str | None, list[str], list[str]]:
            opts = [d for d in decls if d.startswith("-")]
            return self._confarg_name, opts, []

    return _ConfargOption


def _spec_to_option(spec: FlagSpec) -> click.Option:
    """Convert one FlagSpec to a click.Option."""
    try:
        import click as _click
        from click.shell_completion import CompletionItem
    except ImportError as exc:  # pragma: no cover
        msg = "click is required for confarg.cli.click: pip install confarg[click]"
        raise ImportError(msg) from exc

    # Click does not support nargs=-1 for options; use multiple=True instead.
    multiple = spec.nargs == "*"
    nargs: int = 1 if (spec.nargs is None or spec.nargs == "*") else int(spec.nargs)

    type_: Any = _click.Choice(spec.choices) if spec.choices else str

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
            ctx: _click.Context,
            param: _click.Parameter,
            incomplete: str,
        ) -> list[CompletionItem]:
            return [CompletionItem(v) for v in _fn(incomplete)]

        kwargs["shell_complete"] = _shell_complete

    option_cls = _make_option_cls()
    return option_cls(confarg_name=spec.name, **kwargs)


def load_flags_into_command(
    flags: list[FlagSpec],
    command: click.BaseCommand,
) -> None:
    """Load a list of :class:`~confarg.cli.argparse.FlagSpec` objects into a Click command.

    Each spec becomes a :class:`click.Option` appended to ``command.params``.
    Flags whose ``name`` is already registered are silently skipped.
    The ``group`` field of :class:`~confarg.cli.argparse.FlagSpec` is not used —
    Click has no argument-group concept.

    Args:
        flags: The specs to register, typically from :func:`~confarg.cli.argparse.build_static_flags`
            or :func:`~confarg.cli.argparse.build_dynamic_flags`.
        command: The :class:`click.BaseCommand` to populate.
    """
    existing = {p.name for p in command.params}
    for spec in flags:
        if spec.name in existing:
            continue
        command.params.append(_spec_to_option(spec))
        existing.add(spec.name)


def populate_command(  # noqa: PLR0913
    dc_type: type,
    command: click.BaseCommand,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
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
        dc_type: The dataclass type whose fields to register.
        command: The :class:`click.BaseCommand` to populate.
        union_tag: Name of the union discriminator field to skip.
        config_flag: Name of the config-file option (default ``"config"``).
            Set to ``""`` to disable config-file option registration.
        config_subkeys: Whether to register ``--<config_flag>.<field>`` options for
            each direct struct field of the root dataclass (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` option.
        argv: CLI argument list used to pre-resolve ``--<field>.fn`` /
            ``--<field>.class`` values so that callable ``--<field>.bind.*``
            options can be registered before parsing.
    """
    before_names = {p.name for p in command.params}

    static = build_static_flags(dc_type, union_tag=union_tag, config_flag=config_flag, config_subkeys=config_subkeys)
    load_flags_into_command(static, command)
    if argv is not None:
        dynamic = build_dynamic_flags(dc_type, argv, union_tag=union_tag, config_flag=config_flag)
        load_flags_into_command(dynamic, command)

    confarg_names = {p.name for p in command.params} - before_names
    if command.callback is not None and confarg_names:
        _original = command.callback

        @functools.wraps(_original)
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            filtered = {k: v for k, v in kwargs.items() if k not in confarg_names}
            return _original(*args, **filtered)

        command.callback = _wrapped

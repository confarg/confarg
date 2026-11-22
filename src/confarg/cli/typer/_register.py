# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Typer-specific flag loading: load_flags_into_command and populate_command."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Literal, Unpack

import typer.core
from typer._coercion import resolve_type_descriptor
from typer.core import TyperOption
from typer.models import OptionInfo

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from typer._click import Command, Context

    from confarg._defaults import MergeOptions
    from confarg.cli._spec import FlagSpec

from confarg.cli import _clicklike
from confarg.cli._markup import help_escape
from confarg.dictexpr import contains_expression


def _choice_literal(choices: Sequence[str]) -> Any:
    """Return ``Literal[c1, c2, ...]``, the annotation typer reads a choice from."""
    return Literal[tuple(choices)]  # ty: ignore[invalid-type-form]  # dynamic Literal construction at runtime; equivalent to Literal[c1, c2, ...]


def _option_annotation(type_: Any, *, nargs: int, multiple: bool, is_flag: bool) -> Any:
    """Return the annotation typer types an option by, from click's ``type``/``nargs``/``multiple`` keywords."""
    if is_flag:
        return bool
    if multiple:
        return list[type_]
    if nargs > 1:
        return tuple.__class_getitem__((type_,) * nargs)
    return type_


class _TypedOption(TyperOption):
    """A TyperOption built from click's option keywords, which lets an unresolved ``${...}`` through.

    typer types an option by an annotation, which it validates every value against
    through pydantic; this builds that annotation from the ``type`` keyword the shared
    :func:`~confarg.cli._clicklike.option_kwargs` passes, so the shared mapping stays click's.

    Dev Notes:
        docs-dev/architecture/cli-adapters/parity.md#expression-tolerant-choice-gates
    """

    def __init__(self, *, type: Any = str, nargs: int = 1, multiple: bool = False, **kwargs: Any) -> None:  # noqa: A002  # click's keyword
        annotation = _option_annotation(type, nargs=nargs, multiple=multiple, is_flag=bool(kwargs.get("is_flag")))
        super().__init__(
            type_descriptor=resolve_type_descriptor(annotation, OptionInfo()),
            nargs=nargs,
            multiple=multiple,
            **kwargs,
        )

    def process_value(self, ctx: Context, value: Any) -> Any:
        """Pass an expression token through untouched; validate anything else normally."""
        if contains_expression(value):
            return value
        return super().process_value(ctx, value)


class _ConfargOption(_clicklike.DottedNameMixin, _clicklike.StandsBareMixin, _TypedOption):
    """TyperOption subclass taking a dotted name, and a flag that may stand bare."""


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


def _spec_to_option(spec: FlagSpec, *, help_escape: Callable[[str], str] | None = None) -> TyperOption:
    """Convert one FlagSpec to a TyperOption."""
    return _ConfargOption(
        confarg_name=spec.name,
        stands_bare=spec.stands_bare,
        **_clicklike.option_kwargs(
            spec,
            choice_type=_choice_literal,
            completer_kwargs=_completer_kwargs,
            help_escape=help_escape,
        ),
    )


def _option_factory(command: Command) -> Callable[[FlagSpec], TyperOption]:
    """Return the option factory for *command*, escaping confarg's help for the markup typer renders it in.

    typer reads an option's help as markup in the command's ``rich_markup_mode`` when
    rich is in use, and prints it as plain text otherwise.
    """
    mode = getattr(command, "rich_markup_mode", None) if typer.core.HAS_RICH else None
    return functools.partial(_spec_to_option, help_escape=help_escape(mode))


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
    _clicklike.load_flags_into_command(flags, command, _option_factory(command))


def populate_command(
    target: object,
    command: Command,
    *,
    config_subkeys: bool = True,
    **opts: Unpack[MergeOptions],
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
        config_subkeys: Whether to register ``--<config_flag>.<path>`` options for
            every mount point of the target, at any depth (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` option.
        **opts: The sources the options are typed by and how to read them, as for
            :func:`confarg.load`; see :class:`confarg.MergeOptions`. They are recorded,
            so the merge reuses them, and refuses one passed to it that differs: the
            framework splits the command line by the types they give the options. The
            classes ``files``, the environment and the ``--config`` files name type the
            options below the nodes they name. ``argv`` is scanned to register the
            argv-derived dynamic options: ``--<field>.<param>`` for a callable spec,
            ``--<config_flag>.<subpath>[+]`` mounts, list-index / append / delete /
            dict-subkey patches; it defaults to ``sys.argv[1:]``, and ``[]`` registers
            only the static, type-derived options. ``cli_prefix`` is the namespace every
            confarg option lives under, so ``--<prefix>.<field>`` stays distinguishable
            from the host application's own; a non-struct (scalar) target is
            registered as the bare ``--<prefix>`` option, and has no CLI spelling
            without a prefix. ``config_flag`` names the config-file option (``""``
            registers none).
    """
    _clicklike.populate_command(
        target,
        command,
        _option_factory(command),
        "populate_command",
        opts,
        config_subkeys=config_subkeys,
    )

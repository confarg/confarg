# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""FlagSpec-to-option translation shared by the click and typer adapters.

Both frameworks expose the same option-construction keywords, so the mapping from
:class:`~confarg.cli.FlagSpec` lives here once and each adapter supplies only the
three classes its framework spells differently.

Dev Notes:
    docs-dev/architecture/04-cli-adapters.md#the-clicklike-seam
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from confarg.cli._spec import FlagSpec

from confarg.dictexpr import contains_expression


class DottedNameMixin:
    """Allow an option name that is not a valid Python identifier (``--db.host``).

    Mixed in ahead of the framework's own option class.  Both frameworks derive the
    parameter name from its declarations and fall back to ``None`` when the result is
    not an identifier; confarg's names are dotted, so the name is supplied directly
    instead and the declarations are treated as option strings only.
    """

    def __init__(self, confarg_name: str, **kwargs: Any) -> None:
        self._confarg_name = confarg_name
        super().__init__(**kwargs)

    def _parse_decls(self, decls: Sequence[str], expose_value: bool) -> tuple[str, list[str], list[str]]:  # noqa: ARG002, FBT001  # name/type must match the framework's override
        """Return the confarg name verbatim, with every dash-prefixed decl as an opt."""
        return self._confarg_name, [d for d in decls if d.startswith("-")], []


class ExpressionTolerantChoiceMixin:
    """Admit an unresolved ``${...}`` token into a choice-validated option.

    Mixed in ahead of the framework's own choice type, whose ``convert`` validates
    through a normalized mapping rather than the container.  Everything else is
    inherited: ``--help`` still renders the declared values, completion still offers
    them, and a real out-of-domain value still fails with the framework's own error.
    ``build()`` validates the resolved expression.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#expression-tolerant-choice-gates
    """

    def convert(self, value: Any, param: Any, ctx: Any) -> Any:
        """Pass an expression token through untouched; validate anything else normally."""
        if contains_expression(value):
            return value
        return super().convert(value, param, ctx)  # ty: ignore[unresolved-attribute]  # supplied by the choice base


def option_kwargs(
    spec: FlagSpec,
    *,
    choice_cls: Callable[[Sequence[str]], Any],
    completer_kwargs: Callable[[Callable[[str], list[str]]], dict[str, Any]],
) -> dict[str, Any]:
    """Return the framework-agnostic option keywords for one :class:`FlagSpec`.

    The ``group`` field is not used — neither framework has an argument-group concept.

    Args:
        spec: The spec to translate.
        choice_cls: The framework's expression-tolerant choice type, called with the
            spec's choices.
        completer_kwargs: Builds the framework's completion keyword from the spec's
            completer.  The two frameworks disagree here — click takes a
            ``shell_complete`` returning its own completion items, typer takes an
            ``autocompletion`` returning bare strings and deprecates the other — so
            each adapter supplies its own.

    Returns:
        Keywords accepted by both ``click.Option`` and ``typer.core.TyperOption``,
        excluding ``confarg_name``.
    """
    if spec.nargs == 0:
        # Value-less flag (e.g. a list/dict delete --field.N-): a boolean switch.
        return {
            "param_decls": [f"--{spec.name}"],
            "is_flag": True,
            "default": False,
            "required": False,
            "help": spec.help or None,
            "allow_from_autoenv": False,
        }

    # Neither framework supports nargs=-1 for options; use multiple=True instead.
    multiple = spec.nargs == "*"
    kwargs: dict[str, Any] = {
        "param_decls": [f"--{spec.name}"],
        "type": choice_cls(spec.choices) if spec.choices else str,
        "nargs": 1 if (spec.nargs is None or spec.nargs == "*") else int(spec.nargs),
        "multiple": multiple,
        "default": () if multiple else None,
        "required": False,
        "help": spec.help or None,
        "metavar": spec.metavar,
        # confarg handles env vars itself via _parse_env; prevent the framework from
        # also reading them via its auto-envvar prefix.
        "allow_from_autoenv": False,
    }

    if spec.completer is not None:
        kwargs |= completer_kwargs(spec.completer)

    return kwargs

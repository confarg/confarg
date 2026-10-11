# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Framework-agnostic flag descriptions and per-field metadata."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import textwrap
from typing import TYPE_CHECKING, Annotated, Any, NamedTuple, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Callable

from confarg._types import _allows_none, _per_class_cache, _resolve_type, _union_args_no_none
from confarg.exceptions import ConfargError


class HelpParts(NamedTuple):
    """A field's help in the two parts :class:`FlagSpec` keeps apart."""

    #: The field's own help, as its author wrote it.
    prose: str = ""
    #: What confarg adds to it, plain text.
    note: str = ""


@dataclasses.dataclass
class FlagSpec:
    """Framework-agnostic description of a single CLI flag.

    Produced by :func:`~confarg.cli.build_static_flags` and
    :func:`~confarg.cli.build_dynamic_flags`; consumed by
    :func:`~confarg.cli.argparse.load_flags_into_parser` or any other CLI adapter.
    """

    name: str
    """Dotted flag name without ``--``, e.g. ``"db.host"``."""

    nargs: int | str | None = None
    """Argument count: ``None`` = scalar, ``"*"`` = zero-or-more, ``int`` = exact count."""

    whole_value: bool = False
    """The flag also accepts *one* whole-value token in place of its ``nargs`` tokens.

    Set on fixed-arity flags (``tuple[X, Y]``, namedtuple), which vanilla lets a single
    ``'[13, 42]'`` or ``'{"x": 13}'`` token fill.  An adapter grants it only if its
    framework can vary a flag's token count at parse time; click cannot, and declines.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """

    stands_bare: bool = False
    """The flag is legal with no value token at all.

    Set on a collection append (``--<list>+``), which appends nothing and leaves the
    lower-priority sources alone, and on every flag whose type
    :func:`~confarg.cli._build._takes_multi_tokens` calls multi-token -- a field, a dict
    subkey or a collection element -- whether the empty value that leaves clears the
    collection or is the union shaper's missing value to raise (an ``Optional``
    fixed-arity field's flag is the second kind, since its resolved type is a union
    with a sequence variant).  A framework that cannot express a flag taking zero *or*
    more tokens parses an argv with this flag's bare occurrences removed
    (:func:`~confarg.cli._argv.drop_bare_occurrences`).  Nothing is lost: the adapters'
    CLI channel is written by vanilla's loop over the original argv, which reads the
    bare occurrence exactly as vanilla does.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """

    refuses_bare: bool = False
    """:attr:`stands_bare`'s opposite: a bare occurrence of this flag is a missing value.

    Set on a fixed-arity flag -- a ``tuple[X, Y]`` or namedtuple field, and a
    collection element flag addressing one -- asked of the field type *as resolved,
    without unwrapping* ``Optional``: an ``Optional[<fixed-arity>]`` field is a union
    with a sequence variant there, which consumes greedily and is content with no
    token. A framework that reads a bare occurrence as an implicit value asserts the
    moment it meets a real token, so a front-end whose parse cannot tolerate the bare
    occurrence refuses it before parsing, with the missing-value error vanilla raises.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """

    usage: str = "<value>"
    """What the flag's missing-value error names after the flag, e.g. ``"<x> <y>"``.

    Set with :attr:`refuses_bare` to one placeholder per position of the fixed arity,
    the usage vanilla's loop spells for the same flag, so refusing the bare occurrence
    before the framework parses reads exactly as vanilla's refusal does.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """

    bare_error: str | None = None
    """The message a bare occurrence of this config-file flag is refused with.

    Set on every ``--<config_flag>[.<subpath>][+]`` spec to the error vanilla's loop
    raises for it.  An adapter whose framework takes the flag's zero tokens refuses the
    occurrence with it during the framework's own parse.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """

    choices: list[str] | None = None
    """Allowed values (for ``Literal`` / ``Enum`` fields)."""

    metavar: str | None = None
    """Display name shown in help text."""

    help: str = ""
    """The field's own help -- ``FieldMeta.help`` or its attribute docstring -- handed to the framework as written.

    Markup the host's help format reads (cyclopts' Markdown, typer's rich markup) stays live
    in it, as it does in the help the host writes for its own parameters.
    """

    note: str = ""
    """What confarg writes about the flag, printed after :attr:`help` and read as plain text.

    A default's repr, a class path, a dict key, a placeholder: an adapter whose framework
    reads help as markup escapes it for that format (:meth:`rendered_help`), so
    ``(default: '*.py')`` and ``__main__.Cat`` print as written.  Its fixed wording holds no
    markup either: a placeholder is spelled ``--config.FIELD``, never ``--config.<field>``.

    Dev Notes:
        docs-dev/architecture/cli-adapters/framework-specifics.md#help-text-is-format-neutral
    """

    group: str | None = None
    """Argument group title.  ``None`` places the flag at the top level."""

    group_description: str = ""
    """Argument group description (used when creating the group for the first time)."""

    completer: Callable[[str], list[str]] | None = None
    """Optional value completer: ``(prefix) -> [matching_value, ...]``.

    The adapter translates this to its own completion convention
    (e.g. argcomplete wraps it as ``action.completer``).
    """

    hidden: bool = False
    """Keep the flag out of the framework's own help listing, while still accepting it.

    Set on the index spellings of a fixed-length sequence — a namedtuple's per-index
    sub-flags and a tuple's element patches — which patch a position rather than name
    a field, so ``--help`` advertises the name spellings and the usage stays readable.

    Dev Notes:
        docs-dev/architecture/design-decisions/index-spellings-are-hidden-from-help.md#index-spellings-are-hidden-from-help
    """

    def rendered_help(self, escape: Callable[[str], str] | None = None) -> str:
        """Return the help the framework prints: :attr:`help`, then :attr:`note` passed through *escape*.

        Args:
            escape: Turns plain text into the framework's help format, so it prints as
                written (``None`` for a framework that prints help as plain text).
        """
        note = escape(self.note) if escape is not None and self.note else self.note
        return " ".join(part for part in (self.help, note) if part)

    def as_single_token(self) -> FlagSpec:
        """Return this spec reshaped to consume exactly one token, whatever its shape.

        The one inverse of the shape attributes — :attr:`nargs`, :attr:`whole_value`
        and :attr:`stands_bare` — spelled beside them, so a spec forced to a single
        token undoes the multi-token shape in one operation and the next shape
        attribute is reset where it is declared, not by each caller by hand.

        Dev Notes:
            docs-dev/architecture/cli-adapters/flag-model.md#framework-neutral-flag-model
        """
        return dataclasses.replace(self, nargs=None, whole_value=False, stands_bare=False)

    def bare_refusal(self) -> str | None:
        """Return the message a bare occurrence of this flag is refused with, or ``None``.

        :attr:`bare_error` for a config-file flag, vanilla's missing-value error spelled
        with :attr:`usage` for a flag that :attr:`refuses_bare`, and ``None`` for a flag
        whose bare occurrence vanilla accepts or leaves to its framework.

        Dev Notes:
            docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
        """
        if self.bare_error is not None:
            return self.bare_error
        if self.refuses_bare:
            return str(ConfargError.missing_value(f"--{self.name}", self.usage))
        return None


@dataclasses.dataclass
class FieldMeta:
    """Optional per-field metadata for every CLI adapter.

    Attach via ``Annotated``::

        from typing import Annotated
        from confarg.cli import FieldMeta

        @dataclass
        class Config:
            port: Annotated[int, FieldMeta(help="TCP port.", metavar="PORT")]
            \"\"\"Fallback docstring (FieldMeta.help takes precedence).\"\"\"
    """

    help: str | None = None
    metavar: str | None = None


def _get_field_meta(raw_type: Any) -> FieldMeta | None:
    """Return FieldMeta from Annotated[T, FieldMeta(...)] annotation, or None."""
    if get_origin(raw_type) is Annotated:
        for arg in get_args(raw_type)[1:]:
            if isinstance(arg, FieldMeta):
                return arg
    return None


@_per_class_cache
def _get_field_docstrings(dc_type: type) -> dict[str, str]:
    """Extract attribute docstrings (string literals after field defs) via AST.

    For each annotated field in the class body, if the immediately following
    statement is a string constant, that string is treated as the field's
    docstring.  Returns an empty dict when source is unavailable (e.g.
    dynamically created classes).

    Cached per class: before Python 3.13, ``inspect.getsource`` re-parses the whole
    defining module on every call, which dominates a CLI build in a large module.
    The returned dict is shared and must not be mutated.
    """
    try:
        source = inspect.getsource(dc_type)
        source = textwrap.dedent(source)
        tree = ast.parse(source)
    except (OSError, TypeError, IndentationError, SyntaxError):
        return {}

    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == dc_type.__name__):
            continue
        result: dict[str, str] = {}
        stmts = node.body
        for i, stmt in enumerate(stmts):
            if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)):
                continue
            if i + 1 >= len(stmts):
                continue
            next_stmt = stmts[i + 1]
            if (
                isinstance(next_stmt, ast.Expr)
                and isinstance(next_stmt.value, ast.Constant)
                and isinstance(next_stmt.value.value, str)
            ):
                result[stmt.target.id] = inspect.cleandoc(next_stmt.value.value)
        return result
    return {}


def _build_help(  # noqa: PLR0913, PLR0917  # one argument per part of the help
    field_name: str,
    raw_type: Any,
    docstrings: dict[str, str],
    defaults: dict[str, Any],
    flag: str = "",
    position: int | None = None,
) -> HelpParts:
    """Compose the help for one field: its own prose, then confarg's note.

    The prose is FieldMeta.help, else the attribute docstring, else empty.  The note
    holds, in order: ``(index <position>)`` if the field has a *position* (a
    namedtuple's), ``(default: <repr>)`` if it has a dataclass default, and a hint
    about the None sentinel if it is Optional.

    Dev Notes:
        docs-dev/architecture/design-decisions/index-spellings-are-hidden-from-help.md#index-spellings-are-hidden-from-help
    """
    meta = _get_field_meta(raw_type)
    prose = meta.help if meta is not None and meta.help is not None else docstrings.get(field_name, "")

    note: list[str] = []
    if position is not None:
        note.append(f"(index {position})")
    if field_name in defaults:
        note.append(f"(default: {defaults[field_name]!r})")
    if flag and _allows_none(_resolve_type(raw_type)) and _union_args_no_none(_resolve_type(raw_type)):
        note.append("(pass 'none' or 'null' to set to None)")
    return HelpParts(prose.strip(), " ".join(note))

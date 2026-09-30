# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Framework-agnostic flag descriptions and per-field metadata."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import textwrap
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Callable

from confarg._types import _allows_none, _resolve_type, _union_args_no_none


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
    subkey or a collection element -- whose empty value clears the collection.  A framework
    that cannot express a flag taking zero *or* more tokens parses an argv with this flag's
    bare occurrences removed (:func:`~confarg.cli._argv.drop_bare_occurrences`), so what a
    dropped occurrence meant is read back off the original argv: the patch scan honors the
    append, the subkey and the element, and
    :func:`~confarg.cli._collect._bare_multi_token_flags` restores a field flag's clear.
    Marking a flag with no such reader loses what the user typed.

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

    accumulates: bool = False
    """Repeating the flag extends what the earlier occurrences gave, rather than replacing it.

    Set on the multi-token *field* flags — a varlen collection, and a union with a
    sequence variant — because ``--tags x --tags y`` is a second spelling of
    ``--tags x y``.  Which spelling a framework accepts is its own business; what
    repetition *means* is not, so an adapter whose framework keeps only the last
    occurrence has to ask for accumulation (argparse: ``action="extend"``).  Fixed-arity
    flags are excluded: they take one value, and repeating them is last-wins everywhere.

    Dev Notes:
        docs-dev/architecture/cli-adapters/list-syntax-divergence.md#list-syntax-divergence
    """

    choices: list[str] | None = None
    """Allowed values (for ``Literal`` / ``Enum`` fields)."""

    metavar: str | None = None
    """Display name shown in help text."""

    help: str = ""
    """Help text."""

    group: str | None = None
    """Argument group title.  ``None`` places the flag at the top level."""

    group_description: str = ""
    """Argument group description (used when creating the group for the first time)."""

    completer: Callable[[str], list[str]] | None = None
    """Optional value completer: ``(prefix) -> [matching_value, ...]``.

    The adapter translates this to its own completion convention
    (e.g. argcomplete wraps it as ``action.completer``).
    """


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


def _get_field_docstrings(dc_type: type) -> dict[str, str]:
    """Extract attribute docstrings (string literals after field defs) via AST.

    For each annotated field in the class body, if the immediately following
    statement is a string constant, that string is treated as the field's
    docstring.  Returns an empty dict when source is unavailable (e.g.
    dynamically created classes).
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


def _build_help(
    field_name: str,
    raw_type: Any,
    docstrings: dict[str, str],
    defaults: dict[str, Any],
    flag: str = "",
) -> str:
    """Compose the help string for one field.

    Priority: FieldMeta.help > attribute docstring > empty string.
    If the field has a dataclass default, appends ``(default: <repr>)``.
    If the field is Optional, appends a hint about the None sentinel.
    """
    meta = _get_field_meta(raw_type)
    base = meta.help if meta is not None and meta.help is not None else docstrings.get(field_name, "")

    if field_name in defaults:
        suffix = f"(default: {defaults[field_name]!r})"
        base = f"{base} {suffix}".strip() if base else suffix

    if flag and _allows_none(_resolve_type(raw_type)) and _union_args_no_none(_resolve_type(raw_type)):
        none_hint = "(pass 'none' or 'null' to set to None)"
        base = f"{base} {none_hint}".strip() if base else none_hint

    return base

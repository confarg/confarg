# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Framework-agnostic flag descriptions and per-field metadata."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import textwrap
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclasses.dataclass
class FlagSpec:
    """Framework-agnostic description of a single CLI flag.

    Produced by :func:`~confarg.cli.argparse.build_static_flags` and
    :func:`~confarg.cli.argparse.build_dynamic_flags`; consumed by
    :func:`~confarg.cli.argparse.load_flags_into_parser` or any other CLI adapter.
    """

    name: str
    """Dotted flag name without ``--``, e.g. ``"db.host"``."""

    nargs: int | str | None = None
    """Argument count: ``None`` = scalar, ``"*"`` = zero-or-more, ``int`` = exact count."""

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
    """Optional per-field metadata for argparse integration.

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
    from typing import Annotated, get_args, get_origin

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
    from confarg._types import _allows_none, _resolve_type, _union_args_no_none

    meta = _get_field_meta(raw_type)
    base = meta.help if meta is not None and meta.help is not None else docstrings.get(field_name, "")

    if field_name in defaults:
        suffix = f"(default: {defaults[field_name]!r})"
        base = f"{base} {suffix}".strip() if base else suffix

    if flag and _allows_none(_resolve_type(raw_type)) and _union_args_no_none(_resolve_type(raw_type)):
        none_hint = "(pass 'none' or 'null' to set to None)"
        base = f"{base} {none_hint}".strip() if base else none_hint

    return base

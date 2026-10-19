# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""How deep a configuration nests: the one count put to every value before a walker recurses through it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from confarg import _defaults
from confarg._merge import ListOp
from confarg._types import _Pinned
from confarg.exceptions import ConfargError

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from confarg.exceptions import FieldPath

#: The most levels a configuration nests, counted from its root: half of where the costliest
#: walker, construction of a recursive struct, gave up on an empty stack (BUG-248).
MAX_DEPTH: Final = 64


@dataclass(frozen=True)
class Overflow:
    """Where a value first breaks the bound: a position deeper than it, or a container that holds itself.

    *path* is the position; *holder* is, for a value that contains itself, the position of the
    container *path* holds again, an ancestor of *path*, and None otherwise.
    """

    path: FieldPath
    holder: FieldPath | None = None


def overflow(value: Any, at: Sequence[str | int] = ()) -> Overflow | None:
    """Return where *value*, held at the position *at*, nests deeper than :data:`MAX_DEPTH`, or holds itself.

    A dict, a list and a tuple are levels; a key confarg reserves (a file's op key, a cast pin's
    ``__value__``, ``__root__``) and a pending :class:`~confarg.ListOp` are not, nor is a stored
    cast pin, whose value is held at the pin's own position. Counted without recursing, so the
    count never meets the limit it guards, and a container met again at no greater depth is
    not walked again, so a value sharing its parts (YAML aliases) is walked once per part, not
    once per path. A container met again below itself is a value that holds itself.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#a-configuration-nests-at-most-64-levels
    """
    deepest: dict[int, int] = {}  # id of each container walked -> the greatest depth it was walked at
    open_at: dict[int, FieldPath] = {}  # id of each container on the current path -> its position
    stack: list[tuple[Any, FieldPath, bool]] = [(value, tuple(at), False)]
    while stack:
        node, path, leaving = stack.pop()
        if leaving:
            del open_at[id(node)]
            continue
        if len(path) > MAX_DEPTH:
            return Overflow(path)
        children = _children(node, path)
        if children is None:
            continue
        key = id(node)
        if key in open_at:
            return Overflow(path, open_at[key])
        if deepest.get(key, -1) >= len(path):
            continue  # walked already, at this depth or deeper: nothing below it can be deeper now
        deepest[key] = len(path)
        open_at[key] = path
        stack.append((node, path, True))
        stack.extend((child, child_path, False) for child_path, child in reversed(list(children)))
    return None


def _children(node: Any, path: FieldPath) -> Iterator[tuple[FieldPath, Any]] | None:
    """Return the positions and values *node* holds below *path*, or None for a leaf."""
    if isinstance(node, dict):
        return ((path if _no_level(k) else (*path, k), v) for k, v in node.items())
    if isinstance(node, list | tuple):
        return (((*path, i), v) for i, v in enumerate(node))
    if isinstance(node, _Pinned):
        return iter([(path, node.value)])
    return None


def _no_level(key: Any) -> bool:
    """Return whether a dict key holds its value at the dict's own position: an op or a reserved key."""
    return isinstance(key, ListOp) or (isinstance(key, str) and key in _defaults.RESERVED_KEYS)


def refuse_overflow(
    value: Any, action: str, *, at: Sequence[str | int] = (), error: type[ConfargError] = ConfargError
) -> None:
    """Raise *error* if *value*, held at *at*, nests deeper than :data:`MAX_DEPTH` or holds itself.

    *action* says what was being done, for the message: ``read config.yaml``, ``set '--d.json'``,
    ``build Config``.

    Raises:
        ConfargError: Of the class *error*, ``InvalidConfigFileError`` for a document.
    """
    if (found := overflow(value, at)) is None:
        return
    if found.holder is not None:
        raise error.holds_itself(action, found.path, found.holder)
    raise error.too_deep(action, found.path, MAX_DEPTH)


def refuse_long_path(path: Sequence[str | int], spelling: str, *, slack: int = 0) -> None:
    """Raise if a flag's, a variable's or a mount point's *path* is deeper than :data:`MAX_DEPTH`.

    Asked before the path is typed, with a *slack* of one, since a last segment may still turn
    out to be a cast rather than a position; and asked again, with none, of the position it writes.

    Raises:
        ConfargError: If *path* has more than ``MAX_DEPTH + slack`` segments.
    """
    if len(path) > MAX_DEPTH + slack:
        action = f"set {_shortened(spelling)!r}"
        raise ConfargError.too_deep(action, tuple(path), MAX_DEPTH)


def _shortened(spelling: str) -> str:
    """Return *spelling* with its middle elided past 40 characters, as a path is: the flag is as long as its path."""
    if len(spelling) <= 40:  # noqa: PLR2004  # what reads at a glance
        return spelling
    return f"{spelling[:24]} ... {spelling[-12:]}"

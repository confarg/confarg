# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""How deep a configuration nests and how much it copies: the one count every value meets before any walker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from confarg import _defaults, _types  # _types as a module: it imports dictexpr, which imports this one
from confarg._merge import ListOp
from confarg.exceptions import ConfargError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from confarg.exceptions import FieldPath

#: The most levels a configuration nests, counted from its root: half of where the costliest
#: walker, construction of a recursive struct, gave up on an empty stack (BUG-248).
MAX_DEPTH: Final = 64

#: The most positions one configuration copies: at about 45 microseconds and 130 bytes a position through
#: ``load()``, the worst a few hundred bytes can ask stays near 4.5 s and 13 MB (BUG-259).
MAX_COPIED: Final = 100_000


class Copies:
    """The positions one configuration has copied, against :data:`MAX_COPIED`, and what it has read.

    Each public call opens one and passes it down every walk that charges it, so every source,
    channel and resolution of the configuration it reads share it. A location is read once:
    its join, its identity and its document are kept, so reading it again costs the positions
    it copies and nothing else (``_files._load_any``).

    Dev Notes:
        docs-dev/architecture/design-decisions/a-configuration-copies-at-most-100000-positions.md#one-budget-per-configuration
    """

    def __init__(self) -> None:
        self.spent = 0
        #: The location each (including location, written location) pair names (``_sources._join``).
        self.joined: dict[tuple[str | None, str], str] = {}
        #: The identity of each location (``_sources._identity``).
        self.identities: dict[str, str] = {}
        #: The identity of each location read, whose next read copies it.
        self.read: set[str] = set()
        #: Each document read, by its location's identity and the options it was read with.
        self.documents: dict[tuple[str, str], Any] = {}

    @property
    def bound(self) -> int:
        """Return the most positions a configuration copies, :data:`MAX_COPIED`, for a refusal to name."""
        return MAX_COPIED

    @property
    def left(self) -> int:
        """Return how many more positions the configuration may copy."""
        return MAX_COPIED - self.spent

    def charge(self, copied: int, refusal: Callable[[], Exception]) -> None:
        """Count *copied* more positions, raising ``refusal()`` instead when they are more than are left."""
        if copied > self.left:
            raise refusal()
        self.spent += copied


@dataclass(frozen=True)
class Overflow:
    """Where a value first breaks the bound: a position deeper than it, or a container that holds itself.

    *path* is the position; *holder* is, for a value that contains itself, the position of the
    container *path* holds again, an ancestor of *path*, and None otherwise.
    """

    path: FieldPath
    holder: FieldPath | None = None


@dataclass
class Shape:
    """What one walk of a value found: where it breaks the depth bound, and the positions it holds.

    *written* counts the positions below each part where it is first met, *copied* those below
    it, expanded, each time it is met again; *crossed* is the position where *copied* first
    passed the allowance the walk was given, and *crossed_at* what it had counted there.
    """

    overflow: Overflow | None = None
    written: int = 0
    copied: int = 0
    crossed: FieldPath | None = None
    crossed_at: int = 0

    def copy(self, positions: int, path: FieldPath, allowance: int | None) -> None:
        """Count *positions* more copied at *path*, noting where the count first passes *allowance*."""
        self.copied += positions
        if self.crossed is None and allowance is not None and self.copied > allowance:
            self.crossed, self.crossed_at = path, self.copied


_ENTER, _ENTER_COPIED, _LEAVE = range(3)


def overflow(value: Any, at: Sequence[str | int] = ()) -> Overflow | None:
    """Return where *value*, held at the position *at*, nests deeper than :data:`MAX_DEPTH`, or holds itself."""
    return _shape(value, at).overflow


def positions_below(value: Any) -> int:
    """Return how many positions *value* holds below its own, its shared parts expanded."""
    shape = _shape(value)
    return shape.written + shape.copied


def _shape(value: Any, at: Sequence[str | int] = (), allowance: int | None = None) -> Shape:
    """Walk *value*, held at the position *at*, for its depth, its cycles, and the positions it writes and copies.

    A dict, a list and a tuple are levels; a key confarg reserves (a file's op key, a cast pin's
    ``__value__``, ``__root__``) and a pending :class:`~confarg.ListOp` are not, nor is a stored
    cast pin, whose value is held at the pin's own position. Counted without recursing, so the
    count never meets the limit it guards, and a container met again at no greater depth is
    not walked again, so a value sharing its parts (YAML aliases) is walked once per part, not
    once per path: each meeting past the first copies the positions below the part, as
    expanded, which its first walk counted. A container met again below itself is a value that
    holds itself.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#where-it-is-counted
        docs-dev/architecture/design-decisions/a-configuration-copies-at-most-100000-positions.md#what-copies
    """
    deepest: dict[int, int] = {}  # id of each container walked -> the greatest depth it was walked at
    open_at: dict[int, FieldPath] = {}  # id of each container on the current path -> its position
    below: dict[int, int] = {}  # id of each container left -> the positions below it, expanded
    held: dict[int, list[tuple[FieldPath, Any]]] = {}  # id of each container open -> what it holds
    shape = Shape()
    stack: list[tuple[Any, FieldPath, int]] = [(value, tuple(at), _ENTER)]
    while stack:
        node, path, state = stack.pop()
        key = id(node)
        if state == _LEAVE:
            del open_at[key]
            kids = held.pop(key)
            below.setdefault(key, sum(_positions(path, child_at) + below.get(id(child), 0) for child_at, child in kids))
            continue
        if len(path) > MAX_DEPTH:
            return Shape(Overflow(path))
        children = _children(node, path)
        if children is None:
            continue
        if key in open_at:
            return Shape(Overflow(path, open_at[key]))
        met_at = deepest.get(key)
        copying = state == _ENTER_COPIED
        if met_at is not None:
            if not copying:
                shape.copy(below[key], path, allowance)
            if met_at >= len(path):
                continue  # walked already, at this depth or deeper: nothing below it can be deeper now
            copying = True  # walked again for its depth alone: what it holds was counted with it
        deepest[key] = len(path)
        open_at[key] = path
        kids = list(children)
        if met_at is None:
            shape.written += sum(_positions(path, child_at) for child_at, _ in kids)
        held[key] = kids
        stack.append((node, path, _LEAVE))
        stack.extend((child, child_at, _ENTER_COPIED if copying else _ENTER) for child_at, child in reversed(kids))
    return shape


def _positions(path: FieldPath, child_path: FieldPath) -> int:
    """Return 1 when *child_path* is a position below *path*, 0 when the child is held at *path* itself."""
    return int(len(child_path) > len(path))


def _children(node: Any, path: FieldPath) -> Iterator[tuple[FieldPath, Any]] | None:
    """Return the positions and values *node* holds below *path*, or None for a leaf."""
    if isinstance(node, dict):
        return ((path if _no_level(k) else (*path, k), v) for k, v in node.items())
    if isinstance(node, list | tuple):
        return (((*path, i), v) for i, v in enumerate(node))
    if isinstance(node, _types._Pinned):
        return iter([(path, node.value)])
    return None


def _no_level(key: Any) -> bool:
    """Return whether a dict key holds its value at the dict's own position: an op or a reserved key."""
    return isinstance(key, ListOp) or (isinstance(key, str) and key in _defaults.RESERVED_KEYS)


def refuse_overflow(
    value: Any,
    action: str,
    *,
    at: Sequence[str | int] = (),
    error: type[ConfargError] = ConfargError,
    copies: Copies | None = None,
) -> Shape:
    """Raise *error* if *value*, held at *at*, nests deeper than :data:`MAX_DEPTH` or holds itself; return its shape.

    With *copies*, what *value*'s shared parts copy is charged to it, and refused past
    :data:`MAX_COPIED`. *action* says what was being done, for the message: ``read
    config.yaml``, ``set '--d.json'``, ``build Config``.

    Raises:
        ConfargError: Of the class *error*, ``InvalidConfigFileError`` for a document.
    """
    shape = _shape(value, at, None if copies is None else copies.left)
    if (found := shape.overflow) is not None:
        if found.holder is not None:
            raise error.holds_itself(action, found.path, found.holder)
        raise error.too_deep(action, found.path, MAX_DEPTH)
    if copies is not None:
        spent = copies.spent
        copies.charge(
            shape.copied, lambda: error.too_many_copies(action, copies.bound, spent + shape.crossed_at, shape.crossed)
        )
    return shape


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

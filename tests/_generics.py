# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generic classes the tests of FEAT-13 build, importable by the class tags that name them."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, NamedTuple, TypeVar


@dataclass
class Box[T]:
    item: T


@dataclass
class Tagged[T]:
    """A generic base with subclasses, which a class tag selects among."""

    item: T


@dataclass
class Labeled[T](Tagged[T]):
    label: str = ""


@dataclass
class IntTagged(Tagged[int]):
    """Binds its base's parameter itself."""


@dataclass
class Listed[T](Tagged[list[T]]):
    """Binds its base's parameter to a list of its own."""


@dataclass
class Cell[T]:
    item: T


@dataclass
class IntCell(Cell[int]):
    """A non-generic subclass: the field its base declares as T reads as int."""


LegacyT = TypeVar("LegacyT")


@dataclass
class LegacyBase(Generic[LegacyT]):  # noqa: UP046  # the legacy spelling is the case under test
    item: LegacyT


@dataclass
class LegacyWrap(LegacyBase[list[LegacyT]]):
    """Reuses its base's TypeVar for a parameter of its own: each class binds it apart."""

    extra: LegacyT | None = None


@dataclass
class Bounded[T: Box[int]]:
    item: T


@dataclass
class Pair[K, V]:
    key: K
    values: list[V] = field(default_factory=list)
    lookup: dict[K, V] = field(default_factory=dict)


class Handwritten[T]:
    """A plain generic class: its members are its ``__init__``'s parameters."""

    def __init__(self, item: T, items: list[T] | None = None) -> None:
        self.item = item
        self.items = items or []

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and vars(other) == vars(self)

    def __hash__(self) -> int:
        return hash(self.item)


class Point[T](NamedTuple):
    x: T
    y: T


@dataclass
class Dims[*Ts]:
    dims: tuple[*Ts]


@dataclass
class Fn[**P]:
    fn: Callable[P, int]


@dataclass
class Holder:
    b: Box[int]
    bare: Box | None = None
    nested: Box[Box[int]] | None = None
    tagged: Tagged[int] | None = None
    ic: IntCell | None = None
    pair: Pair[str, int] | None = None
    hand: Handwritten[int] | None = None
    point: Point[float] | None = None

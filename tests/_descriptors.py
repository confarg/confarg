# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Descriptor-typed fields the tests of FEAT-40 build, importable by the class tags that name them."""

from collections.abc import Callable
from dataclasses import InitVar, dataclass
from typing import Annotated, Any, Final, overload

from confarg.cli import FieldMeta


@dataclass
class Locator:
    pass


@dataclass
class Pattern(Locator):
    pattern: str


class LocatorField:
    """Hold a Locator; take a str too, as the pattern of one."""

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    def __get__(self, obj: object, objtype: Any = None) -> Locator:
        if obj is None:
            raise AttributeError  # no default: the field is required
        return getattr(obj, self._attr)

    def __set__(self, obj: object, value: Locator | str) -> None:
        setattr(obj, self._attr, Pattern(pattern=value) if isinstance(value, str) else value)


class Converted[T, X]:
    """Hold a T; take an X too, turned into a T by *convert*."""

    def __init__(self, held: type, convert: Callable[[X], T], default: Any = None) -> None:
        self._held = held
        self._convert = convert
        self._default = default

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    def __get__(self, obj: object, objtype: Any = None) -> T:
        if obj is None:
            if self._default is None:
                raise AttributeError
            return self._default
        return getattr(obj, self._attr)

    def __set__(self, obj: object, value: T | X) -> None:
        setattr(obj, self._attr, value if isinstance(value, self._held) else self._convert(value))  # ty: ignore[invalid-argument-type]  # value is an X here


def digits(text: str) -> Any:
    """Return the int *text* spells, whatever the field's parameter is bound to."""
    return int(text)


def square(n: int) -> tuple[int, int]:
    """Return the pair a single side spells."""
    return (n, n)


class Overloaded:
    """A descriptor typed with overloads: ``__get__`` names itself on class access, an int on an instance."""

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    @overload
    def __get__(self, obj: None, objtype: Any = None) -> "Overloaded": ...
    @overload
    def __get__(self, obj: object, objtype: Any = None) -> int: ...
    def __get__(self, obj: object, objtype: Any = None) -> "Overloaded | int":
        if obj is None:
            raise AttributeError
        return getattr(obj, self._attr)

    @overload
    def __set__(self, obj: object, value: int) -> None: ...
    @overload
    def __set__(self, obj: object, value: str) -> None: ...
    def __set__(self, obj: object, value: int | str) -> None:
        setattr(obj, self._attr, int(value))


class Untyped:
    """A descriptor with no annotation: it takes and holds anything."""

    def __set_name__(self, owner, name):  # unannotated on purpose
        self._attr = "_" + name

    def __get__(self, obj, objtype=None):  # unannotated on purpose
        if obj is None:
            raise AttributeError
        return getattr(obj, self._attr)

    def __set__(self, obj, value):  # unannotated on purpose
        setattr(obj, self._attr, value)


class HalfTyped:
    """Overloads annotating one value and not the other: they take ``int | Any``, as a type checker joins them."""

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    def __get__(self, obj: object, objtype: Any = None) -> int:
        if obj is None:
            raise AttributeError
        return getattr(obj, self._attr)

    @overload
    def __set__(self, obj: object, value: int) -> None: ...
    @overload
    def __set__(self, obj, value) -> None: ...  # unannotated on purpose
    def __set__(self, obj: object, value: Any) -> None:
        setattr(obj, self._attr, int(value))


class Validated(property):
    """A ``property`` subclass: its ``__set__`` is C code with no hints, and it returns itself on class access."""


def _held(self: Any) -> int:
    return self._x


def _hold(self: Any, value: int) -> None:
    self._x = int(value)


class WriteOnly:
    """A descriptor with ``__set__`` and no ``__get__``: what it holds, nothing reads back."""

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    def __set__(self, obj: object, value: int) -> None:
        setattr(obj, self._attr, value)


class ReturnsSelf:
    """The descriptor HOWTO's idiom: the descriptor itself on class access, so a dataclass takes it as the default."""

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    def __get__(self, obj: object, objtype: Any = None) -> "Locator | ReturnsSelf":
        if obj is None:
            return self
        return getattr(obj, self._attr)

    def __set__(self, obj: object, value: Locator | str) -> None:
        setattr(obj, self._attr, Pattern(pattern=value) if isinstance(value, str) else value)


@dataclass
class Transform:
    pass


@dataclass
class Resize(Transform):
    size: int


TRANSFORMS = {"resize": Resize(size=3)}


class TransformField:
    """Take a handle only, into an application registry: the object held is no value of what it takes."""

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    def __get__(self, obj: object, objtype: Any = None) -> Transform:
        if obj is None:
            raise AttributeError
        return getattr(obj, self._attr)

    def __set__(self, obj: object, value: str) -> None:
        setattr(obj, self._attr, TRANSFORMS[value])


@dataclass(kw_only=True)
class PartSpec:
    """The installed descriptor: ``locate`` takes ``Locator | str`` and holds a ``Locator``."""

    kind: str = "part"
    locate: LocatorField = LocatorField()


@dataclass(kw_only=True)
class Annotated_:  # named after the shape under test
    """The annotation alone, converted in ``__post_init__``: read as the installed descriptor is."""

    locate: LocatorField

    def __post_init__(self) -> None:
        if isinstance(self.locate, str):
            self.locate = Pattern(pattern=self.locate)


@dataclass(kw_only=True)
class Shapes:
    """Every other shape a descriptor field takes."""

    size: Converted[tuple[int, int], int] = Converted(tuple, square, default=(1, 1))
    count: Overloaded = Overloaded()
    anything: Untyped = Untyped()
    helped: Annotated[LocatorField, FieldMeta(help="where the part is")] = LocatorField()
    optional: LocatorField | None = None


SHAPES_REQUIRED = ["--count", "4", "--anything", "x", "--helped", "h"]
"""The flags ``Shapes`` cannot do without, its descriptors defaulting to nothing."""

type HelpedLocator = Annotated[LocatorField, FieldMeta(help="aliased")]


@dataclass(kw_only=True)
class Qualified:
    """A descriptor under the wrappers every walk sees through: their ``Annotated`` metadata is kept."""

    final: Final[Annotated[LocatorField, FieldMeta(help="final")]] = LocatorField()
    aliased: HelpedLocator = LocatorField()


@dataclass(kw_only=True)
class Joined:
    half: HalfTyped = HalfTyped()


@dataclass(kw_only=True)
class Validating:
    x: Validated = Validated(_held, _hold)  # noqa: RUF009  # a descriptor, which ruff cannot tell from a property subclass


@dataclass(kw_only=True)
class Unreadable:
    x: WriteOnly = WriteOnly()


@dataclass(kw_only=True)
class SelfDefault:
    locate: ReturnsSelf = ReturnsSelf()


@dataclass(kw_only=True)
class Step:
    transform: TransformField = TransformField()


@dataclass(kw_only=True)
class Seeded:
    """An ``InitVar`` annotated by a descriptor: read through ``__set__``, as pyright and ty read it."""

    seed: InitVar[LocatorField]
    pattern: str = ""

    def __post_init__(self, seed: Any) -> None:
        self.pattern = seed if isinstance(seed, str) else seed.pattern


@dataclass(kw_only=True)
class Wrapped[T]:
    """A generic dataclass whose descriptor field names its parameter: bound by the field, then by the descriptor."""

    value: Converted[T, str] = Converted(int, digits)

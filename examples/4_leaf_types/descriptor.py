from dataclasses import dataclass
from typing import Any

import confarg


@dataclass
class Locator:
    """Where to find a part."""


@dataclass
class Pattern(Locator):
    """Find a part by a pattern."""

    pattern: str


class LocatorField:
    """Hold a Locator, given as one or as the pattern of one."""

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    def __get__(self, obj: object, objtype: Any = None) -> Locator:
        if obj is None:
            raise AttributeError  # no default: the field is required
        return getattr(obj, self._attr)

    def __set__(self, obj: object, value: Locator | str) -> None:
        setattr(obj, self._attr, Pattern(pattern=value) if isinstance(value, str) else value)


@dataclass
class Config:
    """Configuration whose locate field takes a str as well as a Locator."""

    locate: LocatorField = LocatorField()


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

from dataclasses import dataclass
from typing import Any

import cyclopts

import confarg.cli.cyclopts as confargcyclopts


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


app = cyclopts.App()
confargcyclopts.populate_app(Config, app, env_prefix="MYAPP_")

if __name__ == "__main__":
    config = confargcyclopts.from_app(Config, app)
    print(config)

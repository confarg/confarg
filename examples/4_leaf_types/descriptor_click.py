from dataclasses import dataclass
from typing import Any

import click

import confarg.cli.click as confargclick


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


@click.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Load and print the configuration."""
    config = confargclick.from_context(Config, ctx)
    print(config)


confargclick.populate_command(Config, run, env_prefix="MYAPP_")

if __name__ == "__main__":
    run()

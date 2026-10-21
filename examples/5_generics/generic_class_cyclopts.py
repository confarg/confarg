from dataclasses import dataclass

import cyclopts

import confarg.cli.cyclopts as confargcyclopts


@dataclass
class Box[T]:
    """A box holding one item of any type."""

    item: T


@dataclass
class Config:
    """Configuration with two boxes, each holding its own type."""

    size: Box[int]
    label: Box[str]


app = cyclopts.App()
confargcyclopts.populate_app(Config, app, env_prefix="MYAPP_")

if __name__ == "__main__":
    config = confargcyclopts.from_app(Config, app)
    print(config)

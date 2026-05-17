from dataclasses import dataclass

import confarg


class BaseClass:
    """A base class."""


class DerivedClass(BaseClass):
    """A derived class."""


class UnrelatedClass:
    """A class unrelated to BaseClass."""


@dataclass
class Config:
    """Top-level application configuration."""

    value: type[BaseClass]


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

from dataclasses import dataclass

import confarg


@dataclass
class Box[T]:
    """A box holding one item of any type."""

    item: T


@dataclass
class Config:
    """Configuration with two boxes, each holding its own type."""

    size: Box[int]
    label: Box[str]


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

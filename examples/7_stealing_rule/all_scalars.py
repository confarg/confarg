"""Example: all scalar types in a union."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Configuration with a union of all scalar types."""

    input: float | bool | str | None


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config)
    pprint(config)


if __name__ == "__main__":
    main()

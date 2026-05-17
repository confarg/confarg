"""Example: str-or-bool union field."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Configuration with a str-or-bool union field."""

    input: str | bool


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config)
    pprint(config)


if __name__ == "__main__":
    main()

"""Example: str-or-int union field."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Configuration with a str-or-int union field."""

    input: str | int


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

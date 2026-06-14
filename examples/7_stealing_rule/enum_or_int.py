"""Example: leaf type coercion for union scalar types."""

from dataclasses import dataclass
from enum import Enum
from pprint import pprint

import confarg


class Value(Enum):
    """Enumeration of possible values."""

    FOO = 1
    BAR = 2


@dataclass
class Config:
    """Configuration with an enum-or-int union field."""

    input: Value | int


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

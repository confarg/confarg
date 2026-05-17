"""Example: leaf type coercion for union scalar types."""

from dataclasses import dataclass
from enum import Enum
from pprint import pprint

import confarg.cli.argparse as confparse


class Value(Enum):
    """Enumeration of possible values."""

    FOO = 1
    BAR = 2


@dataclass
class Config:
    """Configuration with an enum-or-str union field."""

    input: Value | str


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

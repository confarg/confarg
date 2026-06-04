from dataclasses import dataclass
from enum import Enum

import confarg.cli.argparse as confparse


class Value(Enum):
    """Some random Enum."""

    FOO = 1
    BAR = 2


@dataclass
class Config:
    """Configuration with an Enum field."""

    value: Value


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

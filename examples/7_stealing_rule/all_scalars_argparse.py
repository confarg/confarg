"""Example: all scalar types in a union, using argparse integration."""

from dataclasses import dataclass
from pprint import pprint

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Configuration with a union of all scalar types."""

    input: float | bool | str | None


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

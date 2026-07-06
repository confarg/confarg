"""Example: filling a dict-of-ints field from a JSON object."""

from dataclasses import dataclass
from pprint import pprint

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Top-level application configuration."""

    input: dict[str, int]


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options)
    pprint(config)


if __name__ == "__main__":
    main()

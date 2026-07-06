"""Example: filling a list of strings-or-bools, using JSON to pin each item's type."""

from dataclasses import dataclass
from pprint import pprint

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Top-level application configuration."""

    input: list[str | bool]


def main() -> None:
    """Load configuration and print it."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options)
    pprint(config)


if __name__ == "__main__":
    main()

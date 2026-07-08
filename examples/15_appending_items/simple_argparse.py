"""Example: appending to list fields across multiple config files using the key+: syntax."""

from dataclasses import dataclass
from pprint import pprint

from configs import SQLiteConfig

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Top-level application configuration."""

    dbs: list[SQLiteConfig]


def main() -> None:
    """Load configuration and print it."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options)
    pprint(config)


if __name__ == "__main__":
    main()

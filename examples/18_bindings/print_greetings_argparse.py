"""Example: configuring a callable field from CLI/env/config."""

from collections.abc import Callable
from dataclasses import dataclass

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Top-level application configuration."""

    greet_fn: Callable[[str], None]


def main() -> None:
    """Load configuration and invoke the configured greeting function."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options)
    config.greet_fn("world")


if __name__ == "__main__":
    main()

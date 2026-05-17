"""Example: nested dataclass with union dispatch via the class: type."""

from dataclasses import dataclass
from pprint import pprint

from configs import Transform

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Top-level application configuration."""

    transforms: dict[str, Transform]


def main() -> None:
    """Load configuration and print it."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

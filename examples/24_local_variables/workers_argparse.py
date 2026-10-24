"""Example: a local variable's type comes from its declaration."""

from dataclasses import dataclass

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Worker pool sizing, derived from a declared CPU count."""

    workers: int
    reserved: int


def main() -> None:
    """Load configuration and print it."""
    parser = confparse.make_parser(Config, env_prefix="MYAPP_")
    options = parser.parse_args()
    print(confparse.from_namespace(Config, options))


if __name__ == "__main__":
    main()

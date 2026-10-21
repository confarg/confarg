from dataclasses import dataclass

import confarg.cli.argparse as confparse


@dataclass
class Box[T]:
    """A box holding one item of any type."""

    item: T


@dataclass
class Config:
    """Configuration with two boxes, each holding its own type."""

    size: Box[int]
    label: Box[str]


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(Config, env_prefix="MYAPP_")
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options)
    print(config)


if __name__ == "__main__":
    main()

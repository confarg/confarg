"""Example: union of inheritance hierarchies."""

from configs import APIConfig, DBBaseConfig

import confarg.cli.argparse as confparse

type Config = APIConfig | DBBaseConfig


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options)
    print(config)


if __name__ == "__main__":
    main()

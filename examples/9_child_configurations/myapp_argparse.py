"""Example: inheritance-based union dispatch."""

from configs import DBBaseConfig

import confarg.cli.argparse as confparse


def main() -> None:
    """Load and print the database configuration."""
    parser = confparse.make_parser(DBBaseConfig)
    options = parser.parse_args()
    config = confparse.from_namespace(DBBaseConfig, options)
    print(config)


if __name__ == "__main__":
    main()

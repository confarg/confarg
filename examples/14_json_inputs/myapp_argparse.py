"""Example: loading configuration from a JSON file with union-typed and tuple fields."""

from pprint import pprint

from configs.json_input import Config

import confarg.cli.argparse as confparse


def main() -> None:
    """Load configuration and print it."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options)
    pprint(config)


if __name__ == "__main__":
    main()

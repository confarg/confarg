from dataclasses import dataclass
from pprint import pprint

import confarg.cli.argparse as confparse


@dataclass
class Config:
    users: list[str]


def main() -> None:
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

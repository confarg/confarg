from dataclasses import dataclass
from typing import Annotated

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Configuration with an Annotated field."""

    input: Annotated[str, "hello"]


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

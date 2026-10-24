"""Example: local variables as intermediate values for expressions."""

from dataclasses import dataclass

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Application paths, all derived from the same base directory."""

    output_dir: str
    log_dir: str


def main() -> None:
    """Load configuration and print it."""
    parser = confparse.make_parser(Config, env_prefix="MYAPP_")
    options = parser.parse_args()
    print(confparse.from_namespace(Config, options))


if __name__ == "__main__":
    main()

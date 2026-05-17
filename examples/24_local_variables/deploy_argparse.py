"""Example: deriving a local variable from a real, overridable field."""

from dataclasses import dataclass

import confarg.cli.argparse as confparse


@dataclass
class Config:
    """Paths scoped to a deployment environment."""

    deploy_env: str
    output_dir: str
    log_dir: str


def main() -> None:
    """Load configuration and print it."""
    parser = confparse.make_parser(Config, env_prefix="MYAPP_")
    options = parser.parse_args()
    print(confparse.from_namespace(Config, options))


if __name__ == "__main__":
    main()

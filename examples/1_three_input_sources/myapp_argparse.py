from dataclasses import dataclass

import confarg.cli.argparse as confparse


@dataclass
class DBConfig:
    """Database connection settings."""

    host: str
    port: int
    schema_name: str


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(DBConfig)
    options = parser.parse_args()
    config = confparse.from_namespace(DBConfig, options, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

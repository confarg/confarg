"""Example: union type — choose between PostgreSQL and SQLite config."""

from dataclasses import dataclass

import confarg.cli.argparse as confparse


@dataclass
class DBServerConfig:
    """DB server connection configuration."""

    host: str
    port: int
    name: str


@dataclass
class SQLiteConfig:
    """SQLite file-based database configuration."""

    dbpath: str


type Config = SQLiteConfig | DBServerConfig


def main() -> None:
    """Load and print the database configuration."""
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

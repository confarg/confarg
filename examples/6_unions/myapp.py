"""Example: union type — choose between PostgreSQL and SQLite config."""

from dataclasses import dataclass

import confarg


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
    config = confarg.load(Config)
    print(config)


if __name__ == "__main__":
    main()

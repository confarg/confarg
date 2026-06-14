"""Example: union with Literal tag fields for explicit discrimination."""

from dataclasses import dataclass
from typing import Literal

import confarg


@dataclass(kw_only=True)
class PostgreConfig:
    """PostgreSQL connection configuration with a 'postgre' tag."""

    tag: Literal["postgre"] = "postgre"
    host: str
    port: int
    name: str


@dataclass(kw_only=True)
class MariaDBConfig:
    """MariaDB connection configuration with a 'mariadb' tag."""

    tag: Literal["mariadb"] = "mariadb"
    host: str
    port: int
    name: str


type Config = PostgreConfig | MariaDBConfig


def main() -> None:
    """Load and print the database configuration."""
    config = confarg.load(Config)
    print(config)


if __name__ == "__main__":
    main()

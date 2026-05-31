"""First example: load a simple dataclass from CLI/env/config."""

from dataclasses import dataclass

import confarg


@dataclass
class DBConfig:
    """Database connection configuration."""

    host: str
    port: int
    schema_name: str


def main() -> None:
    """Load and print the database configuration."""
    db_config = confarg.load(DBConfig, env_prefix="MYAPP_")
    print(db_config)


if __name__ == "__main__":
    main()

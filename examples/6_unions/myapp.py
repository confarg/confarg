"""Example: union type — choose between PostgreSQL and SQLite config."""

from configs import PostgreSQLConfig, SQLiteConfig

import confarg

type Config = PostgreSQLConfig | SQLiteConfig


def main() -> None:
    """Load and print the database configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

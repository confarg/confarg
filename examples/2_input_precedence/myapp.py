from dataclasses import dataclass

import confarg


@dataclass
class DBConfig:
    """Database connection settings."""

    host: str
    port: int
    schema_name: str


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(DBConfig, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

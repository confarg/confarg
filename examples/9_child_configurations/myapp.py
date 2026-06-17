"""Example: inheritance-based union dispatch."""

from configs import DBBaseConfig

import confarg


def main() -> None:
    """Load and print the database configuration."""
    config = confarg.load(DBBaseConfig, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

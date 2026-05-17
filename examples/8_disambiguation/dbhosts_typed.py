"""Example: union with Literal type fields for explicit discrimination."""

from configs import MariaDBConfigTyped, PostgreSQLConfigTyped

import confarg

type Config = MariaDBConfigTyped | PostgreSQLConfigTyped


def main() -> None:
    """Load and print the database configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

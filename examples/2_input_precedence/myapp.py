from configs import PostgreSQLConfig

import confarg


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(PostgreSQLConfig, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

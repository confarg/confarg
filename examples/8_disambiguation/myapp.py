from configs import PostgreSQLConfig, SQLiteConfig

import confarg

type Config = PostgreSQLConfig | SQLiteConfig


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

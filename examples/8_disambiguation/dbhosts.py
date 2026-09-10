from configs import MariaDBConfig, PostgreSQLConfig

import confarg

type Config = MariaDBConfig | PostgreSQLConfig


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

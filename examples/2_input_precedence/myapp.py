from configs import PostgreSQLConfig

import confarg


def main() -> None:
    config = confarg.load(PostgreSQLConfig, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

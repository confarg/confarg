from configs import DBBaseConfig

import confarg


def main() -> None:
    config = confarg.load(DBBaseConfig, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

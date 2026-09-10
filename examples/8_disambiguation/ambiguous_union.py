from dataclasses import dataclass

import confarg


@dataclass(kw_only=True)
class ConfigStr:
    input: str


@dataclass(kw_only=True)
class ConfigInt:
    input: int


type Config = ConfigStr | ConfigInt


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

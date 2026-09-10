from dataclasses import dataclass

import confarg


@dataclass
class Config:
    value: str | type


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

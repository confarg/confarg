from dataclasses import dataclass

import confarg


class BaseClass:
    pass


class DerivedClass(BaseClass):
    pass


class UnrelatedClass:
    pass


@dataclass
class Config:
    value: type[BaseClass]


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

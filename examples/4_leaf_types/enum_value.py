from dataclasses import dataclass
from enum import Enum

import confarg


class Value(Enum):
    FOO = 1
    BAR = 2


@dataclass
class Config:
    value: Value


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

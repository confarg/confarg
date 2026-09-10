from dataclasses import dataclass
from enum import Enum
from pprint import pprint

import confarg


class Value(Enum):
    FOO = 1
    BAR = 2


@dataclass
class Config:
    input: Value | int


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

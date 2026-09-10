from dataclasses import dataclass
from pprint import pprint

from configs import Transform

import confarg


@dataclass
class Config:
    transforms: list[Transform]


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

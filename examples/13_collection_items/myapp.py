from dataclasses import dataclass
from pprint import pprint

from configs import DBBaseConfig

import confarg


@dataclass
class Config:
    dbs: list[DBBaseConfig]


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

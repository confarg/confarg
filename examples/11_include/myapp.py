from dataclasses import dataclass
from pprint import pprint
from typing import Literal

from configs import DBBaseConfig

import confarg


@dataclass
class Config:
    db: DBBaseConfig
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

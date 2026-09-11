from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    input: dict[str, int]


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

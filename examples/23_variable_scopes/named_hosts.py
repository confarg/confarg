from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Host:
    name: str
    port: int


@dataclass
class Config:
    hosts: dict[str, Host]


def main() -> None:
    config = confarg.load(Config)
    pprint(config)


if __name__ == "__main__":
    main()

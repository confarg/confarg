from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Database:
    host: str
    port: int


@dataclass
class Service:
    database: Database


@dataclass
class Config:
    database: Database
    service: Service


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)
    print("same object:", config.service.database is config.database)


if __name__ == "__main__":
    main()

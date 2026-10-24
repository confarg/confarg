from dataclasses import dataclass
from datetime import date, datetime, timedelta

import confarg


@dataclass
class Config:
    day: date
    start: datetime
    every: timedelta


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)
    print(confarg.dump(config))


if __name__ == "__main__":
    main()

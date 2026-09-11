from dataclasses import dataclass
from typing import Final, Literal

import confarg


@dataclass
class Config:
    final: Final[Literal["hello"]] = "hello"


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

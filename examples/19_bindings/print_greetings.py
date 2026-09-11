from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    greet_fn: Callable[[str], None]


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    config.greet_fn("world")


if __name__ == "__main__":
    main()

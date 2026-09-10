from collections.abc import Callable, Iterable
from dataclasses import dataclass

from optimizer import BaseOptimizer

import confarg


@dataclass
class Config:
    optimizer: Callable[[Iterable], BaseOptimizer]


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config.optimizer([]))


if __name__ == "__main__":
    main()

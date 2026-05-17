"""Example: factory functions for callable configuration fields."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from optimizer import BaseOptimizer

import confarg


@dataclass
class Config:
    """Application configuration with an optimizer factory callable."""

    optimizer: Callable[[Iterable], BaseOptimizer]


def main() -> None:
    """Load configuration and print the configured optimizer."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config.optimizer([]))


if __name__ == "__main__":
    main()

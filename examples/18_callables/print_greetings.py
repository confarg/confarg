"""Example: configuring a callable field from CLI/env/config."""

from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    """Top-level application configuration."""

    greet_fn: Callable[[str], None]


def main() -> None:
    """Load configuration and invoke the configured greeting function."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    config.greet_fn("world")


if __name__ == "__main__":
    main()

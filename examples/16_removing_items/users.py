"""Example: nested dataclass with union dispatch via the class: type."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Top-level application configuration."""

    users: list[str]


def main() -> None:
    """Load configuration and print it."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

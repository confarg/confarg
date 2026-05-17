"""Example: loading configuration from a JSON file with union-typed and tuple fields."""

from dataclasses import dataclass
from pprint import pprint

from configs import DBBaseConfig

import confarg


@dataclass
class Config:
    """Top-level application configuration."""

    db: DBBaseConfig


def main() -> None:
    """Load configuration and print it."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

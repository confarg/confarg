"""Example: loading configuration into nested dataclasses via dot-separated CLI args and config files."""

from dataclasses import dataclass
from pprint import pprint
from typing import Literal

from configs import DBBaseConfig

import confarg


@dataclass
class Config:
    """Top-level application configuration."""

    db: DBBaseConfig
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def main() -> None:
    """Load configuration and print it."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

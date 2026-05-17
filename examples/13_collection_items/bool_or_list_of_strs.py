"""Example: loading list, tuple, and union-typed fields from CLI args and config files."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Top-level application configuration."""

    input: bool | list[str]


def main() -> None:
    """Load configuration and print it."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

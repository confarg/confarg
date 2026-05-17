"""Example: filling a dict-of-ints field from a JSON object."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Top-level application configuration."""

    input: dict[str, int]


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

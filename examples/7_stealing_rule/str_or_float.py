"""Example: str-or-float union field."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Configuration with a str-or-float union field."""

    input: str | float


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

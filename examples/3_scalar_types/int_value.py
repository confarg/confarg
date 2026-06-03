from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Configuration with an int field."""

    value: int


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config)
    pprint(config)


if __name__ == "__main__":
    main()

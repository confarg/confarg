from dataclasses import dataclass
from enum import Enum

import confarg


class Value(Enum):
    """Some random Enum."""

    FOO = 1
    BAR = 2


@dataclass
class Config:
    """Configuration with an Enum field."""

    value: Value


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

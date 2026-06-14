from dataclasses import dataclass
from typing import Literal

import confarg


@dataclass
class Config:
    """Configuration with a Literal["16", 16] field."""

    value: Literal["16", 16]


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config)
    print(config)


if __name__ == "__main__":
    main()

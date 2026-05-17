from dataclasses import dataclass
from typing import Final, Literal

import confarg


@dataclass
class Config:
    """Configuration with a Final[Literal] field."""

    final: Final[Literal["hello"]] = "hello"


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config)
    print(config)


if __name__ == "__main__":
    main()

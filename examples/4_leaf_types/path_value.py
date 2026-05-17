from dataclasses import dataclass
from pathlib import Path

import confarg


@dataclass
class Config:
    """Configuration with a Path field."""

    value: Path


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config)
    print(config)


if __name__ == "__main__":
    main()

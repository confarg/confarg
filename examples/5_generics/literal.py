from dataclasses import dataclass
from typing import Literal

import confarg


@dataclass
class Config:
    """Configuration with a Literal field."""

    input: Literal["hello", "world"]


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

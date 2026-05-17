"""Example: scalar type coercion."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Configuration with various scalar type fields."""

    value_none: None = None
    value_int: int = 0
    value_bool: bool = False
    value_float: float = 0.0
    value_str: str = ""


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config)
    pprint(config)


if __name__ == "__main__":
    main()

"""Example: union with Literal type fields for explicit discrimination."""

from dataclasses import dataclass

import confarg


@dataclass(kw_only=True)
class ConfigStr:
    """Configuration with a string input."""

    input: str


@dataclass(kw_only=True)
class ConfigInt:
    """Configuration with an integer input."""

    input: int


type Config = ConfigStr | ConfigInt


def main() -> None:
    """Load and print the database configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

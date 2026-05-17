from dataclasses import dataclass

import confarg


@dataclass
class Config:
    """Top-level application configuration."""

    value: str | type


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

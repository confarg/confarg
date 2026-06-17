"""Example: union of inheritance hierarchies."""

from configs import APIConfig, DBBaseConfig

import confarg

type Config = APIConfig | DBBaseConfig


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

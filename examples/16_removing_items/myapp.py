"""Example: deleting list elements and fields across config files using the key-: syntax."""

from pprint import pprint

from configs.deletion import Config

import confarg


def main() -> None:
    """Load configuration and print it."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

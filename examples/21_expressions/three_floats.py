"""Example: using ${field.path} expressions to interpolate values across config fields."""

from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    """Top-level application configuration."""

    value1: float
    value2: float
    value3: float


def main() -> None:
    """Load configuration and print it."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)

    # For saving purpose:
    config_dict = confarg.merge(Config)
    # merge() returns the raw dict with ${...} strings intact — save it to preserve expressions
    confarg.dump_file(config_dict, "saved_config_uninterpolated.yaml")
    config = confarg.build(Config, config_dict)
    # from_dict() resolves expressions; dump_file() then serializes the resolved values
    confarg.dump_file(config, "saved_config_interpolated.yaml")


if __name__ == "__main__":
    main()

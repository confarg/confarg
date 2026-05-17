from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class SubConfig:
    value1: float
    value2: float


@dataclass
class Config:
    value: float
    values: SubConfig


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)

    config_dict = confarg.merge(Config)
    confarg.dump_file(config_dict, "saved_config_uninterpolated.yaml")
    config = confarg.build(Config, config_dict)
    confarg.dump_file(config, "saved_config_interpolated.yaml")


if __name__ == "__main__":
    main()

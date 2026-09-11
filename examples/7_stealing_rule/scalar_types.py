from dataclasses import dataclass
from pprint import pprint

import confarg


@dataclass
class Config:
    value_none: None = None
    value_int: int = 0
    value_bool: bool = False
    value_float: float = 0.0
    value_str: str = ""


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()

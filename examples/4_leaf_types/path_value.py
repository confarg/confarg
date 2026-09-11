from dataclasses import dataclass
from pathlib import Path

import confarg


@dataclass
class Config:
    value: Path


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    num_labels: int = 2
    tokenize: Callable[[str], list[str]] = str.split


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(f"{config.num_labels} labels")
    print(config.tokenize("the dog and the cat"))


if __name__ == "__main__":
    main()

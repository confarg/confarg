from dataclasses import dataclass

import confarg


@dataclass
class Config:
    workers: int
    reserved: int


def main() -> None:
    print(confarg.load(Config, env_prefix="MYAPP_"))


if __name__ == "__main__":
    main()

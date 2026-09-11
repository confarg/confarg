from dataclasses import dataclass

import confarg


class Int:
    def __init__(self, value: int | None) -> None:
        self.value = value

    def __repr__(self) -> str:
        return f"Int(value={self.value})"


def coerce_int(value: str) -> Int:
    return Int(None if value == "NaN" else int(value))


@dataclass
class Config:
    input: Int


def main() -> None:
    confarg.register_leaf_type(Int, coerce_int)
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

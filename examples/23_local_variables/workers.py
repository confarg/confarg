"""Example: a local variable's type comes from its declaration."""

from dataclasses import dataclass

import confarg


@dataclass
class Config:
    """Worker pool sizing, derived from a declared CPU count."""

    workers: int
    reserved: int


def main() -> None:
    """Load configuration and print it."""
    print(confarg.load(Config, env_prefix="MYAPP_"))


if __name__ == "__main__":
    main()

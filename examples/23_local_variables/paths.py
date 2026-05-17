"""Example: local variables as intermediate values for expressions."""

from dataclasses import dataclass

import confarg


@dataclass
class Config:
    """Application paths, all derived from the same base directory."""

    output_dir: str
    log_dir: str


def main() -> None:
    """Load configuration and print it."""
    print(confarg.load(Config, env_prefix="MYAPP_"))


if __name__ == "__main__":
    main()

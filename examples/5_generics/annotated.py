from dataclasses import dataclass
from typing import Annotated

import confarg


@dataclass
class Config:
    """Configuration with an Annotated field."""

    input: Annotated[str, "hello"]


def main() -> None:
    """Load and print the configuration."""
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

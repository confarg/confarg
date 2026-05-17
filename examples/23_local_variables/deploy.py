"""Example: deriving a local variable from a real, overridable field."""

from dataclasses import dataclass

import confarg


@dataclass
class Config:
    """Paths scoped to a deployment environment."""

    deploy_env: str
    output_dir: str
    log_dir: str


def main() -> None:
    """Load configuration and print it."""
    print(confarg.load(Config, env_prefix="MYAPP_"))


if __name__ == "__main__":
    main()

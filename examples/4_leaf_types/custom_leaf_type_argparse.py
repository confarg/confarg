from dataclasses import dataclass

import confarg
import confarg.cli.argparse as confparse


class Int:
    """Custom integer wrapper that supports NaN."""

    def __init__(self, value: int | None) -> None:
        self.value = value

    def __repr__(self) -> str:
        return f"Int(value={self.value})"


def coerce_int(value: str) -> Int:
    """Coerce a string to Int, treating 'NaN' as None."""
    return Int(None if value == "NaN" else int(value))


@dataclass
class Config:
    """Configuration with an Enum field."""

    input: Int


def main() -> None:
    """Load and print the configuration."""
    confarg.register_leaf_type(Int, coerce_int)
    parser = confparse.make_parser(Config)
    options = parser.parse_args()
    config = confparse.from_namespace(Config, options, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

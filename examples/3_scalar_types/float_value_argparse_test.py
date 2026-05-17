from argparse import ArgumentParser
from dataclasses import dataclass
from pprint import pprint


@dataclass
class Config:
    """Configuration with a float field."""

    value: float


def main() -> None:
    """Load and print the configuration."""
    parser = ArgumentParser(allow_abbrev=True)
    parser.add_argument("--value", type=float)
    options = parser.parse_args()
    pprint(options)


if __name__ == "__main__":
    main()

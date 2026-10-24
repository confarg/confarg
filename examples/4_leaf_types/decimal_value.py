from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import confarg


@dataclass
class Config:
    price: Decimal
    id: UUID


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()

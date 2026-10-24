from dataclasses import dataclass
from typing import Literal


@dataclass(kw_only=True)
class MariaDBConfig:
    host: str
    port: int = 3306
    schema_name: str


@dataclass(kw_only=True)
class MariaDBConfigTyped:
    type: Literal["mariadb"] = "mariadb"
    host: str
    port: int = 3306
    schema_name: str

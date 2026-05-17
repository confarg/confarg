from dataclasses import dataclass
from typing import Literal

from .dbbaseconfig import DBBaseConfig


@dataclass(kw_only=True)
class PostgreSQLConfig:
    host: str
    port: int = 5432
    schema_name: str


@dataclass(kw_only=True)
class PostgreSQLConfigTyped:
    type: Literal["postgres"] = "postgres"
    host: str
    port: int = 5432
    schema_name: str


@dataclass(kw_only=True)
class PostgreSQLConfigChild(DBBaseConfig):
    host: str
    port: int = 5432
    schema_name: str

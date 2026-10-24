from dataclasses import dataclass

from .dbbaseconfig import DBBaseConfig


@dataclass
class SQLiteConfig:
    dbpath: str


@dataclass(kw_only=True)
class SQLiteConfigChild(DBBaseConfig):
    dbpath: str

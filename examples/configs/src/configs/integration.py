"""Shared database dataclasses for the 90_integration example."""

from dataclasses import dataclass


@dataclass
class DBConfig:
    """Abstract base for database configuration variants."""


@dataclass
class DBServerConfig(DBConfig):
    """Network-based database connection (host/port)."""

    host: str
    port: int
    name: str


@dataclass
class SQLiteConfig(DBConfig):
    """File-based SQLite database configuration."""

    dbpath: str

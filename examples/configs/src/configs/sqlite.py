# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass

from .dbbaseconfig import DBBaseConfig


@dataclass
class SQLiteConfig:
    """SQLite file-based database configuration."""

    dbpath: str


@dataclass(kw_only=True)
class SQLiteConfigChild(DBBaseConfig):
    """SQLite configuration sharing a common base class."""

    dbpath: str

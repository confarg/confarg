# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared dataclasses for the confarg examples.

One submodule per example directory, so class tags in configs and on the
command line read as e.g. ``configs.nested.SQLiteConfig`` instead of the
module-dependent ``__main__.SQLiteConfig``.
"""

from .api import APIConfig
from .dbbaseconfig import DBBaseConfig
from .mariadb import MariaDBConfig, MariaDBConfigTyped
from .postgres import PostgreSQLConfig, PostgreSQLConfigChild, PostgreSQLConfigTyped
from .sqlite import SQLiteConfig, SQLiteConfigChild

__all__ = [
    "APIConfig",
    "DBBaseConfig",
    "MariaDBConfig",
    "MariaDBConfigTyped",
    "PostgreSQLConfig",
    "PostgreSQLConfigChild",
    "PostgreSQLConfigTyped",
    "SQLiteConfig",
    "SQLiteConfigChild",
]

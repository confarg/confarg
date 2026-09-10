# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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
    type: Literal["postgres"]
    host: str
    port: int = 5432
    schema_name: str


@dataclass(kw_only=True)
class PostgreSQLConfigChild(DBBaseConfig):
    host: str
    port: int = 5432
    schema_name: str

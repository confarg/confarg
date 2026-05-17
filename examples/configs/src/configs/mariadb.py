# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from typing import Literal


@dataclass(kw_only=True)
class MariaDBConfig:
    """MariaDB connection configuration."""

    host: str
    port: int = 3306
    schema_name: str


@dataclass(kw_only=True)
class MariaDBConfigTyped:
    """MariaDB connection configuration with a 'mariadb' type."""

    type: Literal["mariadb"] = "mariadb"
    host: str
    port: int = 3306
    schema_name: str

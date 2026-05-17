# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A tool to manage complex configurations.

> Load and resolve complex configurations from files, environment variables and command line arguments. Keep your data
> structures and favorite CLI library.
"""

from __future__ import annotations

from confarg import exceptions
from confarg._api import build, dump, dump_file, from_dict, load, merge, resolve
from confarg._types import TagPolicy

__all__ = [  # noqa: RUF022
    # Two-step API
    "merge",
    "build",
    # Three-step API (dict-centric)
    "resolve",
    "from_dict",
    # One-step convenience
    "load",
    # Dump
    "dump",
    "dump_file",
    # Types
    "TagPolicy",
    # Exceptions / warnings
    "exceptions",
]

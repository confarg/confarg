# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Symbol import by dotted path."""

from __future__ import annotations

import importlib
from typing import Any

from confarg.exceptions import SymbolImportError


def _import_dotted(path: str) -> Any:
    """Import an object by dotted path, trying decreasing module prefixes.

    Tries importing the longest valid module prefix first, then chains
    getattr for the remaining parts.
    """
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        module_path = ".".join(parts[:i])
        try:
            obj = importlib.import_module(module_path)
        except ImportError:
            continue
        except Exception as e:
            msg = f"Cannot import {path!r}: error loading module '{module_path}': {e}"
            raise SymbolImportError(msg) from e
        try:
            for attr in parts[i:]:
                obj = getattr(obj, attr)
        except AttributeError as e:
            msg = f"Cannot import {path!r}: {e}"
            raise SymbolImportError(msg) from e
        else:
            return obj
    msg = f"Cannot import {path!r}: no importable module found in path"
    raise SymbolImportError(msg)

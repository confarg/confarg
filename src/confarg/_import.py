# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Symbol import by dotted path."""

from __future__ import annotations

import builtins
import importlib
from typing import Any

from confarg.exceptions import SymbolImportError


def _import_dotted(path: str) -> Any:
    """Import an object by dotted path, trying decreasing module prefixes.

    Tries importing the longest valid module prefix first, then chains
    getattr for the remaining parts.  As a final fallback, resolves the path
    against the ``builtins`` module so bare builtin names (``int``, ``str``,
    ``list``, ...) work without a ``builtins.`` prefix.
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
    # No importable module prefix matched; fall back to builtins so a bare
    # name like "int" resolves.  Real modules take priority (loop above), and
    # no builtin name collides with an importable module name.
    try:
        obj = builtins
        for attr in parts:
            obj = getattr(obj, attr)
    except AttributeError:
        pass
    else:
        return obj
    msg = f"Cannot import {path!r}: no importable module found in path"
    raise SymbolImportError(msg)

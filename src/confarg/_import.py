# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Symbol import by dotted path."""

from __future__ import annotations

import builtins
import importlib
from typing import Any

from confarg.exceptions import SymbolImportError

_NOT_FOUND = object()


def _prefix_not_importable(e: ModuleNotFoundError, module_path: str) -> bool:
    """True when ``module_path`` itself (or an ancestor) is the module not found.

    A ``ModuleNotFoundError`` carries the name of the module the import machinery
    could not find in ``name``. When that is ``module_path`` or one of its
    ancestors, the prefix is simply not an importable module — try a shorter
    one. When it is anything else, ``module_path`` exists but a transitive
    dependency it imports is missing, which is a real error to surface.
    """
    name = e.name
    return name is not None and (name == module_path or module_path.startswith(name + "."))


def _import_dotted(path: str) -> Any:
    """Import an object by dotted path, trying decreasing module prefixes.

    Tries importing the longest valid module prefix first, then chains
    getattr for the remaining parts.  As a final fallback, resolves the path
    against the ``builtins`` module so bare builtin names (``int``, ``str``,
    ``list``, ...) work without a ``builtins.`` prefix.

    A failure raised *inside* an importable module is kept distinct from "this
    prefix is not a module": only a ``ModuleNotFoundError`` whose ``name`` is the
    prefix itself or one of its ancestors means the prefix is simply not
    importable (try a shorter one). Any other failure — a broken transitive
    dependency, a failed ``from x import y``, a circular import — comes from a
    module that does exist and is surfaced as
    :class:`~confarg.exceptions.SymbolImportError` rather than masked as a
    typo'd path. See docs-dev/architecture/05-types-and-construction.md#dotted-imports.
    """
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        module_path = ".".join(parts[:i])
        try:
            obj = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            # `name` is the module the import machinery could not find. When it
            # is `module_path` or an ancestor of it, the prefix itself is not
            # importable — try a shorter prefix. Otherwise the module exists but
            # a transitive dependency it imports is missing: surface that
            # instead of masking it as a typo'd path.
            if _prefix_not_importable(e, module_path):
                continue
            msg = f"Cannot import {path!r}: error loading module '{module_path}': {e}"
            raise SymbolImportError(msg) from e
        except Exception as e:
            # A non-``ModuleNotFoundError`` failure (bare ``ImportError`` from a
            # failed ``from x import y``, circular import, or any other error
            # raised while executing the module) comes from a module that does
            # exist, so surface it rather than walking down to shorter prefixes.
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
    # name like "int" resolves.  See docs-dev/architecture/05-types-and-construction.md#dotted-imports.
    obj = _resolve_builtin(parts)
    if obj is not _NOT_FOUND:
        return obj
    msg = f"Cannot import {path!r}: no importable module found in path"
    raise SymbolImportError(msg)


def _resolve_builtin(parts: list[str]) -> Any:
    """Resolve a dotted path against the ``builtins`` module, or return a sentinel.

    Lets bare builtin names (``int``, ``str``, ``list``, ...) work without a
    ``builtins.`` prefix. Returns ``_NOT_FOUND`` when no attribute chain matches,
    so a name that resolves to ``None`` (the ``None`` builtin) is still a hit.
    """
    try:
        obj = builtins
        for attr in parts:
            obj = getattr(obj, attr)
    except AttributeError:
        return _NOT_FOUND
    return obj

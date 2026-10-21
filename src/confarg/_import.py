# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Symbol import by dotted path."""

from __future__ import annotations

import builtins
import functools
import importlib
import inspect
from typing import Any

from confarg.exceptions import SymbolImportError, SymbolNotFoundError

_NOT_FOUND = object()


def dotted_name(obj: Any) -> str:
    """Return the dotted path that :func:`_import_dotted` resolves back to *obj*.

    The one writer of a dotted name, so it cannot disagree with the reader beside it.
    ``__qualname__``, not ``__name__``: a class nested inside another class is reached
    as ``Outer.Inner``, and the tag confarg writes has to be one it can import. A bound
    method is named through the class it is bound to (the class itself for a class
    method), since its qualified name names the class that defines it, which may be a base.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#dotted-imports
    """
    if inspect.ismethod(obj):
        owner = obj.__self__ if isinstance(obj.__self__, type) else type(obj.__self__)
        return f"{dotted_name(owner)}.{obj.__name__}"
    return f"{obj.__module__}.{obj.__qualname__}"


def imports_back(path: str, obj: Any) -> bool:
    """Check that :func:`_import_dotted` resolves *path* to *obj* itself, or to an object equal to it.

    Equality, for a class method: it is a new bound method on each access. What a dump writes
    is checked this way before it is written, since a qualified name holding ``<locals>`` or
    ``<lambda>``, or a name the module rebinds, has no import that leads back.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back
    """
    try:
        named = _import_dotted(path)
    except SymbolImportError:
        return False
    return bool(named is obj or named == obj)


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

    An undotted name is looked up in ``builtins`` only, never imported: a module is no class
    and no callable, so importing one could only run its code. A string that is no dotted
    path of identifiers names nothing and imports nothing either.

    A failure raised *inside* an importable module is kept distinct from "this
    prefix is not a module": only a ``ModuleNotFoundError`` whose ``name`` is the
    prefix itself or one of its ancestors means the prefix is simply not
    importable (try a shorter one). Any other failure — a broken transitive
    dependency, a failed ``from x import y``, a circular import — comes from a
    module that does exist and is surfaced as
    :class:`~confarg.exceptions.SymbolImportError` rather than masked as a
    typo'd path.

    Raises:
        SymbolNotFoundError: If nothing answers to *path*: no module, no attribute, or no
            dotted path of identifiers at all.
        SymbolImportError: If a module on *path* exists but fails while it is imported.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#dotted-imports
        docs-dev/architecture/types/dotted-imports.md#a-path-names-nothing-or-a-module-fails
    """
    parts = path.split(".")
    if not all(part.isidentifier() for part in parts):
        msg = f"Cannot import {path!r}: not a dotted path of identifiers"
        raise SymbolNotFoundError(msg)
    # An undotted name is never imported: it is looked up in builtins alone, below.
    module_prefixes = range(len(parts), 0, -1) if len(parts) > 1 else range(0)
    for i in module_prefixes:
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
            obj = functools.reduce(getattr, parts[i:], obj)
        except AttributeError as e:
            msg = f"Cannot import {path!r}: {e}"
            raise SymbolNotFoundError(msg) from e
        else:
            return obj
    # No importable module prefix matched; fall back to builtins so a bare
    # name like "int" resolves.  See docs-dev/architecture/types/dotted-imports.md#dotted-imports.
    obj = _resolve_builtin(parts)
    if obj is not _NOT_FOUND:
        return obj
    msg = f"Cannot import {path!r}: no importable module found in path"
    raise SymbolNotFoundError(msg)


def _resolve_builtin(parts: list[str]) -> Any:
    """Resolve a dotted path against the ``builtins`` module, or return a sentinel.

    Lets bare builtin names (``int``, ``str``, ``list``, ...) work without a
    ``builtins.`` prefix. Returns ``_NOT_FOUND`` when no attribute chain matches,
    so a name that resolves to ``None`` (the ``None`` builtin) is still a hit.
    """
    try:
        return functools.reduce(getattr, parts, builtins)
    except AttributeError:
        return _NOT_FOUND

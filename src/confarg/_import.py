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
    A C type's method has no ``__module__``, and is named through the class that owns it
    (:func:`_c_owner`).

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#dotted-imports
    """
    if inspect.ismethod(obj):
        owner = obj.__self__ if isinstance(obj.__self__, type) else type(obj.__self__)
        return f"{dotted_name(owner)}.{obj.__name__}"
    if (owner := _c_owner(obj)) is not None:
        return f"{dotted_name(owner)}.{obj.__name__}"
    return f"{obj.__module__}.{obj.__qualname__}"


def has_dotted_name(obj: Any) -> bool:
    """True if :func:`dotted_name` spells a path for *obj*: it has a module, or a C type owns it.

    Whether the path imports back is :func:`imports_back`'s to say.
    """
    return _c_owner(obj) is not None or bool(getattr(obj, "__module__", None))


def _c_owner(obj: Any) -> type | None:
    """Return the class whose C method *obj* is, or None.

    A method descriptor or a slot wrapper names it by ``__objclass__`` (``str.upper``,
    ``int.__add__``), a builtin class method by ``__self__`` (``dict.fromkeys``). A builtin
    bound to a module or an instance (``len``, ``"abc".upper``) has none, and neither has a C
    static method (``str.maketrans``), whose ``__self__`` is None.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#a-c-types-method-is-named-through-its-class
    """
    owner = getattr(obj, "__objclass__", None)
    if owner is None and inspect.isbuiltin(obj):
        owner = obj.__self__
    return owner if isinstance(owner, type) else None


def imports_back(path: str, obj: Any) -> bool:
    """Check that :func:`_import_dotted` resolves *path* to *obj* itself, or to an object equal to it.

    Equality, for a class method: it is a new bound method on each access. What a dump writes
    is checked this way before it is written, since a qualified name holding ``<locals>`` or
    ``<lambda>``, or a name the module rebinds, has no import that leads back. A
    ``RecursionError`` or a ``MemoryError`` the import raises passes through, as it does
    out of :func:`_import_dotted`.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back
    """
    try:
        named = _import_dotted(path)
    except SymbolImportError:
        return False
    return bool(named is obj or named == obj)


def _import_dotted(path: str) -> Any:
    """Import an object by dotted path: its longest module prefix, then the attributes after it.

    The prefixes are imported shortest first, so the first one whose import raises is the
    module that failed, which the error names. Every ancestor of a module is one, so the walk
    stops at the first prefix that is not, and the parts after it are attributes. As a final
    fallback, resolves the path against the ``builtins`` module so bare builtin names
    (``int``, ``str``, ``list``, ...) work without a ``builtins.`` prefix.

    An undotted name is looked up in ``builtins`` only, never imported: a module is no class
    and no callable, so importing one could only run its code. A string that is no dotted
    path of identifiers names nothing and imports nothing either.

    A failure raised *inside* an importable module is kept distinct from "this
    prefix is not a module": only a ``ModuleNotFoundError`` whose ``name`` is the
    prefix itself or one of its ancestors means the prefix is simply not
    importable. Any other failure — a broken transitive dependency, a failed
    ``from x import y``, a circular import — comes from a module that does exist
    and is surfaced as :class:`~confarg.exceptions.SymbolImportError` rather than
    masked as a typo'd path. A ``RecursionError`` or a ``MemoryError`` passes
    through as it is: the module's code or the caller's stack may have raised it.

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
    module, length = _longest_module_prefix(path, parts) if len(parts) > 1 else (None, 0)
    if module is not None:
        try:
            return functools.reduce(getattr, parts[length:], module)
        except AttributeError as e:
            msg = f"Cannot import {path!r}: {e}"
            raise SymbolNotFoundError(msg) from e
    # No importable module prefix matched; fall back to builtins so a bare
    # name like "int" resolves.  See docs-dev/architecture/types/dotted-imports.md#dotted-imports.
    obj = _resolve_builtin(parts)
    if obj is not _NOT_FOUND:
        return obj
    msg = f"Cannot import {path!r}: no importable module found in path"
    raise SymbolNotFoundError(msg)


def _longest_module_prefix(path: str, parts: list[str]) -> tuple[Any, int]:
    """Import the prefixes of *parts* shortest first, and return the module the longest names and its length.

    The module is None, of length 0, when the first part names no module. The length counts
    parts, since a module's ``__name__`` may not be the path that reached it (``os.path``).

    Raises:
        SymbolImportError: If a prefix is a module that fails while it is imported, named in
            the message.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#a-path-names-nothing-or-a-module-fails
    """
    module = None
    for i in range(1, len(parts) + 1):
        module_path = ".".join(parts[:i])
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            # `name` is the module the import machinery could not find. When it is `module_path`,
            # the prefix is not a module, and the parts after the last one are attributes: its
            # ancestors all imported before it. Otherwise the module exists but a dependency it
            # imports is missing: surface that instead of masking it as a typo'd path.
            if e.name == module_path:
                return module, i - 1
            msg = f"Cannot import {path!r}: error loading module '{module_path}': {e}"
            raise SymbolImportError(msg) from e
        except (RecursionError, MemoryError):
            raise
        except Exception as e:
            # A non-``ModuleNotFoundError`` failure (bare ``ImportError`` from a
            # failed ``from x import y``, circular import, or any other error
            # raised while executing the module) comes from a module that does exist.
            msg = f"Cannot import {path!r}: error loading module '{module_path}': {e}"
            raise SymbolImportError(msg) from e
    return module, len(parts)


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

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Symbol import by dotted path."""

from __future__ import annotations

import builtins
import functools
import importlib
import inspect
import sys
from typing import TYPE_CHECKING, Any

from confarg.exceptions import SymbolImportError, SymbolNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

_NOT_FOUND = object()

# The modules CPython publishes a private or a platform module's objects through, which no
# attribute of that module names. A top-level stdlib ``_x`` is published through ``x``.
_PUBLIC_FACES = {
    "nt": ("os", "os.path"),
    "posix": ("os", "os.path"),
    "ntpath": ("os.path",),
    "posixpath": ("os.path",),
    "genericpath": ("os.path",),
    "_thread": ("threading",),
    "builtins": ("types",),
}


def dotted_name(obj: Any) -> str:
    """Return the dotted path that :func:`_import_dotted` resolves back to *obj*.

    The one writer of a dotted name, so it cannot disagree with the reader beside it.
    An object defined in a class keeps the rest of its ``__qualname__``: a class nested
    inside another class is reached as ``Outer.Inner``, and the tag confarg writes has to be
    one it can import. A bound method is named through the class it is bound to (the class
    itself for a class method), since its qualified name names the class that defines it,
    which may be a base. A C type's method has no ``__module__``, and is named through the
    class that owns it (:func:`_c_owner`). The path goes through the first module that
    publishes the object, when one does (:func:`_public_path`), so it depends on what the
    modules publish when it is written: finding it may import a stdlib module and run a lazy
    module ``__getattr__`` for the object's own name. A ``RecursionError`` or a
    ``MemoryError`` raised there passes through, as it does out of :func:`imports_back`.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#dotted-imports
    """
    if inspect.ismethod(obj):
        owner = obj.__self__ if isinstance(obj.__self__, type) else type(obj.__self__)
        return f"{dotted_name(owner)}.{obj.__name__}"
    if (owner := _c_owner(obj)) is not None:
        return f"{dotted_name(owner)}.{obj.__name__}"
    return _public_path(obj)


def _public_path(obj: Any) -> str:
    """Return the path of *obj* through the first module that publishes it and imports back.

    An object defined in a class is published with its outermost holder, the class its
    qualified name starts with. The modules are tried in :func:`_public_homes`' order, and
    the module that defines *obj* is the path when none publishes it.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#a-path-names-the-module-that-publishes-the-object
    """
    home, qualname = obj.__module__, obj.__qualname__
    head, dot, rest = qualname.partition(".")
    holder = obj
    if dot:
        defining = sys.modules.get(home)
        holder = None if defining is None else vars(defining).get(head)
    if holder is not None:
        for module_name, module in _public_homes(home):
            name = _published_name(module, holder)
            if name is not None and imports_back(path := f"{module_name}.{name}{dot}{rest}", obj):
                return path
    return f"{home}.{qualname}"


def _public_homes(home: str) -> Iterator[tuple[str, ModuleType]]:
    """Yield the modules that may publish an object *home* defines, with their paths, in the order they are tried.

    CPython's public face of *home* first (``_PUBLIC_FACES``, or ``x`` for a stdlib ``_x``),
    then *home*'s ancestors shortest first, then *home* itself: a package publishes what its
    submodules define, and a submodule's layout may differ across platforms and versions.
    A public face is imported, as a stdlib module named by convention, never by data; *home*
    and its ancestors were imported with it, and one that is not loaded publishes nothing.
    """
    faces = _PUBLIC_FACES.get(home, ())
    if not faces and home.startswith("_") and home[1:] in sys.stdlib_module_names:
        faces = (home[1:],)
    for face in faces:
        try:
            yield face, importlib.import_module(face)
        except ImportError:
            continue
    parts = home.split(".")
    for module_name in (".".join(parts[:i]) for i in range(1, len(parts) + 1)):
        if (module := sys.modules.get(module_name)) is not None:
            yield module_name, module


def _published_name(module: ModuleType, obj: Any) -> str | None:
    """Return the name *module* publishes *obj* under, or None.

    A module publishes the names ``from module import *`` takes: its ``__all__``, or every name
    not starting with ``_``. The object's own name is read with ``getattr``, which runs a lazy
    module ``__getattr__`` for that name alone, as importing the path back does; another name is
    found in the module's namespace, which runs none.
    """
    declared = getattr(module, "__all__", None)
    names = declared if declared is not None else [n for n in vars(module) if not n.startswith("_")]
    own = getattr(obj, "__name__", None)
    if isinstance(own, str) and own in names and _held(module, own) is obj:
        return own
    namespace = vars(module)
    return next((name for name in names if name in namespace and namespace[name] is obj), None)


def _held(module: ModuleType, name: str) -> Any:
    """Return what *module* holds under *name*, or ``_NOT_FOUND``, running its lazy ``__getattr__`` for *name*.

    A hook that fails holds nothing under the name, so a path is never written through it, and
    the message or the dump that asked for the path is not replaced by the hook's error. A
    ``RecursionError`` or a ``MemoryError`` passes through, as it does out of :func:`_import_dotted`.
    """
    try:
        return getattr(module, name, _NOT_FOUND)
    except (RecursionError, MemoryError):
        raise
    except Exception:  # noqa: BLE001 — a lazy hook that fails publishes nothing under the name
        return _NOT_FOUND


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

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A tool to manage complex configurations.

> Load and resolve complex configurations from files, environment variables and command line arguments. Keep your data
> structures and favorite CLI library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from confarg import exceptions
from confarg._api import build, dump, dump_file, from_dict, load, merge, resolve
from confarg._types import TagPolicy
from confarg.typedload._coerce import _LEAF_COERCIONS, _LEAF_SERIALIZERS


def register_leaf_type(
    tp: type,
    coerce: Callable[[Any], Any],
    *,
    serialize: Callable[[Any], Any] = str,
) -> None:
    """Register a custom leaf type.

    After registration, ``tp`` is treated as a leaf in both directions: values of
    that type can appear as scalars in config files, env vars, and CLI args, and
    they are written back as scalars by ``dump()`` and ``dump_file()``, even if
    ``tp`` would otherwise be constructed field by field as a class.

    ``coerce`` is called with the raw input value — either a ``str`` subclass
    from CLI, env and CSV sources, or the natively-parsed Python object from
    config files — and must return an instance of ``tp``, raising ``ValueError``,
    ``TypeError`` or ``OSError`` on failure.  Values that already are instances of
    ``tp`` are used as-is.  Unresolved ``${...}`` expressions are never passed to
    ``coerce``; it receives their resolved value.

    ``serialize`` is the inverse: it is called with an instance of ``tp`` and must
    return a value a config file can hold (a string, number or bool), which
    ``coerce`` accepts back.  It defaults to ``str``, which is right for types
    whose ``str()`` is their wire form (``UUID``, ``Decimal``, ``Path``) and wrong
    for types whose ``__str__`` is a ``repr``-style debugging aid — pass an
    explicit callable for those, or dumps will not load back.

    Example::

        from uuid import UUID
        confarg.register_leaf_type(UUID, UUID)            # str() is the wire form

        confarg.register_leaf_type(Int, coerce_int, serialize=lambda i: i.value)
    """
    _LEAF_COERCIONS[tp] = coerce
    _LEAF_SERIALIZERS[tp] = serialize


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
    # Leaf-type extension
    "register_leaf_type",
    # Exceptions / warnings
    "exceptions",
]

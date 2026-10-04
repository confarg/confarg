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
from confarg._defaults import MergeOptions
from confarg._sources import register_scheme as _register_scheme
from confarg._sources import unregister_scheme as _unregister_scheme
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


def register_scheme(scheme: str, read: Callable[[str], bytes]) -> None:
    """Register a handler that reads config sources for a URL scheme.

    After registration, any location beginning ``<scheme>:`` can be used wherever a
    configuration file path can: ``files=``, ``env_config``, ``<PREFIX>CONFIG__<SUBPATH>``,
    ``--config[.subpath][+]`` and ``__include__``.

    ``read`` is called with the full location string exactly as it was written --
    ``"gs://bucket/path/config.yaml"`` -- and must return the document's raw ``bytes``.
    confarg decodes them itself, so a handler never chooses an encoding: that keeps a BOM
    working in JSON and CSV, which a decoded ``str`` would break.  Raise ``OSError`` (or
    ``confarg.exceptions.InvalidConfigFileError``) when the document cannot be read; anything
    else propagates unchanged.

    The format is still chosen by the extension of the location's path, so a handler is not
    asked about it and a location with no extension is rejected.  Relative ``__include__``
    paths inside a document fetched this way resolve against its own location and may not
    leave its scheme and host.

    ``file``, ``http``, ``https`` and ``s3`` are registered already (``s3`` needs boto3:
    ``pip install confarg[s3]``).  Registering one of those names again replaces it, which is
    how an application adds authentication, a different timeout, or caching.

    Example::

        import urllib.request

        def read_authenticated(location: str) -> bytes:
            request = urllib.request.Request(location, headers={"Authorization": TOKEN})
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()

        confarg.register_scheme("https", read_authenticated)   # replace the built-in
        confarg.register_scheme("gs", read_gcs)                # or add a new scheme
    """
    _register_scheme(scheme, read)


def unregister_scheme(scheme: str) -> None:
    """Remove the reader registered for a URL scheme, a built-in one included.

    A location naming the scheme afterwards is refused the way any unknown scheme is, with
    ``InvalidConfigFileError`` naming the schemes that remain -- from every channel, since the
    registry is global.  ``unregister_scheme("http")`` and ``unregister_scheme("https")`` are
    therefore how an application forbids loading configuration over the network at all::

        confarg.unregister_scheme("http")
        confarg.unregister_scheme("https")
        confarg.load(Config, files=["https://cfg.example.com/app.yaml"])  # raises

    The scheme name is matched case-insensitively and may be written with its separator
    (``"HTTP"``, ``"http:"`` and ``"http://"`` all name the same entry).

    Removing a scheme is not how a handler is replaced -- pass the new reader to
    :func:`register_scheme` instead, which overwrites in place.

    Raises:
        ValueError: If no reader is registered for the scheme. Removing what is not there is a
            mistake worth hearing about rather than a silent no-op, because the usual cause is a
            misspelled scheme name and the silent version leaves the scheme loadable.
    """
    _unregister_scheme(scheme)


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
    "MergeOptions",
    "TagPolicy",
    # Leaf-type extension
    "register_leaf_type",
    # Config-source extension
    "register_scheme",
    "unregister_scheme",
    # Exceptions / warnings
    "exceptions",
]

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Config source locations: scheme dispatch, reading, format, relative resolution, identity.

A location is a string -- a local path, or a URL whose scheme names a registered handler. This
module answers every question a location implies, so no caller branches on local versus remote.

Dev Notes:
    docs-dev/architecture/config-files/locations-and-schemes.md#locations-and-schemes
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from collections.abc import Callable

from confarg.exceptions import InvalidConfigFileError

#: A location is a URL only when at least two characters precede the colon, so a Windows drive
#: letter stays a path. See docs-dev/architecture/config-files/locations-and-schemes.md#locations-and-schemes.
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]+:")

#: Seconds the built-in HTTP reader waits. An application needing another value registers its
#: own http/https handler over this one.
_HTTP_TIMEOUT = 10.0

#: Hosts a file:// URL may name; anything else is refused rather than silently dropped.
_LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1"})

#: The one HTTP status with a better error than "unreachable".
_HTTP_NOT_FOUND = 404


def _read_local(loc: str) -> bytes:
    """Return the bytes of a local filesystem path."""
    return Path(loc).read_bytes()


def _read_file_url(loc: str) -> bytes:
    """Return the bytes named by a ``file:`` URL.

    Accepts ``file:/p``, ``file:///p``, ``file://localhost/p`` and ``file:///C:/p``. Translation
    to a filesystem path is ``urllib.request.url2pathname``'s, and therefore platform-dependent.

    Raises:
        InvalidConfigFileError: If the URL names a host other than localhost.
    """
    # url2pathname is soft-deprecated from 3.14 in favour of Path.from_uri, which does not exist
    # on this project's minimum (3.12) and rejects the single-slash `file:/p` form this accepts.
    from urllib.request import url2pathname  # noqa: PLC0415  # ty: ignore[deprecated]  # see above

    parts = urlsplit(loc)
    if parts.netloc.lower() not in _LOCAL_HOSTS:
        msg = (
            f"file:// URL names the host {parts.netloc!r}: confarg reads file:// URLs on the local"
            f" machine only. Use a plain path for a network share."
        )
        raise InvalidConfigFileError(msg)
    return _read_local(url2pathname(parts.path))  # ty: ignore[deprecated]  # 3.12 has no replacement


def _read_http(loc: str) -> bytes:
    """Return the bytes served at an ``http``/``https`` URL, using the stdlib only.

    Raises:
        InvalidConfigFileError: If the server answers 404, or the request otherwise fails.
    """
    from urllib.error import HTTPError, URLError  # noqa: PLC0415  # stdlib, imported where used
    from urllib.request import urlopen  # noqa: PLC0415  # stdlib, imported where it is used

    try:
        # S310 asks that the scheme be audited: the registry admits only http/https here.
        with urlopen(loc, timeout=_HTTP_TIMEOUT) as response:  # noqa: S310
            return bytes(response.read())
    except HTTPError as e:
        if e.code == _HTTP_NOT_FOUND:
            raise InvalidConfigFileError.not_found(loc) from None
        raise InvalidConfigFileError.unreachable(loc, e) from e
    except (URLError, OSError) as e:
        raise InvalidConfigFileError.unreachable(loc, e) from e


def _read_s3(loc: str) -> bytes:
    """Return the bytes of an ``s3://bucket/key`` object, via boto3 and its credential chain.

    Raises:
        InvalidConfigFileError: If boto3 is not installed, the object does not exist, or the
            request fails.
    """
    try:
        import boto3  # noqa: PLC0415  # optional dependency, imported only to read an s3:// URL
        from botocore.exceptions import BotoCoreError, ClientError  # noqa: PLC0415  # ships with boto3
    except ImportError:
        msg = "boto3"
        raise InvalidConfigFileError.missing_library(msg, "confarg[s3]", "loading s3:// config files") from None

    parts = urlsplit(loc)
    bucket, key = parts.netloc, parts.path.lstrip("/")
    if not bucket or not key:
        msg = f"Malformed S3 location {loc}: expected s3://bucket/path/to/config.yaml"
        raise InvalidConfigFileError(msg)
    try:
        body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"]
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "NoSuchBucket", "404"):
            raise InvalidConfigFileError.not_found(loc) from None
        raise InvalidConfigFileError.unreachable(loc, e) from e
    except BotoCoreError as e:
        raise InvalidConfigFileError.unreachable(loc, e) from e
    with body:
        return bytes(body.read())


#: Readers by scheme. ``register_scheme`` and ``unregister_scheme`` are the only writers;
#: re-registering a built-in is how an application adds a timeout, authentication or caching, and
#: removing one is how it forbids a scheme outright.
_SCHEME_READERS: dict[str, Callable[[str], bytes]] = {
    "file": _read_file_url,
    "http": _read_http,
    "https": _read_http,
    "s3": _read_s3,
}


def _normalize_scheme(scheme: str) -> str:
    """Return the registry key for *scheme*: lowercased, without a trailing ``:`` or ``//``.

    The one place a user-supplied scheme name becomes a key, so ``"HTTPS://"``, ``"https:"`` and
    ``"https"`` name one entry whichever entry point they arrive through.

    Raises:
        ValueError: If the result is not a usable scheme name.
    """
    name = scheme.lower().rstrip(":/")
    if not name or _SCHEME_RE.match(f"{name}:") is None:
        msg = (
            f"Invalid scheme {scheme!r}: a scheme starts with a letter, continues with letters,"
            f" digits, '+', '.' or '-', and is at least two characters long (one character would"
            f" collide with a Windows drive letter)."
        )
        raise ValueError(msg)
    return name


def register_scheme(scheme: str, read: Callable[[str], bytes]) -> None:
    """Register a reader for a URL scheme. See :func:`confarg.register_scheme`."""
    _SCHEME_READERS[_normalize_scheme(scheme)] = read


def unregister_scheme(scheme: str) -> None:
    """Remove a registered reader for a URL scheme. See :func:`confarg.unregister_scheme`."""
    name = _normalize_scheme(scheme)
    if name not in _SCHEME_READERS:
        listed = ", ".join(sorted(_SCHEME_READERS)) or "none"
        msg = f"No reader is registered for the config source scheme {scheme!r}. Registered: {listed}."
        raise ValueError(msg)
    del _SCHEME_READERS[name]


def _scheme_of(loc: str) -> str:
    """Return the registered scheme *loc* names, or the empty string when it is a local path.

    Raises:
        InvalidConfigFileError: If *loc* names a scheme no handler is registered for.

    Dev Notes:
        docs-dev/architecture/config-files/locations-and-schemes.md#locations-and-schemes
    """
    match = _SCHEME_RE.match(loc)
    if match is None:
        return ""
    scheme = match.group()[:-1].lower()
    if scheme not in _SCHEME_READERS:
        raise InvalidConfigFileError.unknown_scheme(scheme, list(_SCHEME_READERS))
    return scheme


def _read_bytes(loc: str) -> bytes:
    """Return the raw bytes of the document at *loc*.

    The single place a read failure becomes an ``InvalidConfigFileError``, for every scheme and
    every channel, so no loader carries its own not-found branch.

    Dev Notes:
        docs-dev/architecture/config-files/locations-and-schemes.md#locations-and-schemes
    """
    scheme = _scheme_of(loc)
    reader = _SCHEME_READERS[scheme] if scheme else _read_local
    try:
        return reader(loc)
    except InvalidConfigFileError:
        raise
    except FileNotFoundError:
        raise InvalidConfigFileError.not_found(loc) from None
    except OSError as e:
        raise InvalidConfigFileError.unreachable(loc, e) from e


def _suffix(loc: str) -> str:
    """Return the lowercased extension *loc* dispatches its format on.

    A URL's query and fragment are stripped first, so ``https://h/app.yaml?env=prod`` is YAML.

    Dev Notes:
        docs-dev/architecture/config-files/locations-and-schemes.md#locations-and-schemes
    """
    inner = urlsplit(loc).path if _scheme_of(loc) else loc
    return Path(inner).suffix.lower()


def _identity(loc: str) -> str:
    """Return the key deciding whether two locations name the same document.

    Used for include-cycle detection. A local path resolves; a URL drops its fragment, which
    addresses a position inside a document rather than a document.
    """
    if not _scheme_of(loc):
        return str(Path(loc).resolve())
    scheme, netloc, path, query, _ = urlsplit(loc)
    return urlunsplit((scheme, netloc, path, query, ""))


def _join(base: str | None, relative: str) -> str:
    """Return the absolute location a *relative* include names inside the document at *base*.

    A *relative* carrying its own registered scheme is already absolute and is returned as-is --
    unless *base* is remote, where leaving its origin is refused.

    *base* is ``None`` for the channel routes -- ``--config``, ``CONFIG__<PATH>`` and ``files=``
    -- which have no including document and resolve against the process working directory
    instead. That is the one difference between them and ``__include__``
    (docs-dev/architecture/config-files/mounting.md#mounting).

    Raises:
        InvalidConfigFileError: If a remote document names a location outside its own origin.

    Dev Notes:
        docs-dev/architecture/config-files/locations-and-schemes.md#relative-includes-resolve-within-one-origin
    """
    if base is None or not _scheme_of(base):
        # A local document may name any registered location, or a path relative to its own, and
        # a channel route starts from the process working directory. The join resolves, so an
        # error or a cycle names the absolute file, not `a/../b/c.yaml`.
        if _scheme_of(relative):
            return relative
        directory = Path.cwd() if base is None else Path(base).parent
        return str((directory / relative).resolve())
    base_scheme = _scheme_of(base)
    if _SCHEME_RE.match(relative) is not None:
        # Scheme-bearing, so absolute: another origin by construction, registered or not.
        raise InvalidConfigFileError.cross_origin_include(base, relative)
    _, netloc, path, _, _ = urlsplit(base)
    joined = relative if relative.startswith("/") else posixpath.join(posixpath.dirname(path), relative)
    return urlunsplit((base_scheme, netloc, posixpath.normpath(joined), "", ""))


def _location(value: Any) -> str:
    """Return *value* as a location string, accepting the ``str | Path`` the public API takes."""
    return value if isinstance(value, str) else str(value)

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exception and warning classes for confarg."""

from __future__ import annotations

from typing import Any


class ConfargError(Exception):
    """Base exception for all confarg errors."""


class MissingFieldError(ConfargError):
    """Raised when a required field is not provided by any source."""


class SymbolImportError(ConfargError):
    """Raised when a dotted import path cannot be resolved.

    Distinct from :class:`TypeCoercionError` because the problem is with the
    import path itself (typo, missing module, attribute not found), not with a
    value that failed type conversion.
    """


class TypeCoercionError(ConfargError):
    """Raised when a value cannot be coerced to the target type."""

    @classmethod
    def cannot_coerce(cls, src: str, value: Any, tp: str, path: str) -> TypeCoercionError:
        """Return an error for a value that cannot be coerced to the target type."""
        return cls(f"Cannot coerce {src} {value!r} to {tp} at '{path}'")


class InvalidConfigFileError(ConfargError):
    """Raised for config file issues: not found, malformed, or unsupported format."""

    @classmethod
    def not_found(cls, path: Any) -> InvalidConfigFileError:
        """Return an error for a config file that does not exist."""
        return cls(f"Config file not found: {path}")

    @classmethod
    def malformed(cls, fmt: str, path: Any, exc: Any) -> InvalidConfigFileError:
        """Return an error for a config file that failed to parse."""
        return cls(f"Malformed {fmt}: {path}: {exc}")

    @classmethod
    def missing_library(cls, lib: str, pkg: str, action: str) -> InvalidConfigFileError:
        """Return an error when an optional parser library is not installed."""
        return cls(f"{lib} is required for {action}. Install it with: pip install {pkg}")

    @classmethod
    def unsupported_format(cls, ext: str) -> InvalidConfigFileError:
        """Return an error for a config file extension that confarg cannot load."""
        return cls(f"Unsupported config file format: {ext!r}. Supported formats: .yaml/.yml, .toml, .json")


class UnknownArgumentError(ConfargError):
    """Raised when an unrecognized CLI argument is encountered."""


class AmbiguousUnionError(ConfargError):
    """Raised when a Union cannot be disambiguated by structure and no tag is provided."""


class CircularReferenceError(ConfargError):
    """Raised when expression references form a cycle in the dependency graph."""


class MissingReferenceError(ConfargError):
    """Raised when an expression references a field path that does not exist."""

    @classmethod
    def field_not_found(cls, path: str, detail: str | None = None) -> MissingReferenceError:
        """Return an error for an expression reference to a missing field path."""
        base = f"Field '{path}' not found"
        return cls(f"{base}: {detail}") if detail is not None else cls(f"{base} in configuration")


class UnsafeExpressionError(ConfargError):
    """Raised when an expression contains disallowed AST nodes or function calls."""


class ExpressionEvalError(ConfargError):
    """Raised for runtime errors during expression evaluation."""


class ConfargWarning(UserWarning):
    """Emitted for non-fatal configuration issues.

    Currently raised when an environment variable matches the configured prefix
    but does not correspond to any known field on the target type.  Convert to
    errors in your test-suite via::

        warnings.filterwarnings("error", category=confarg.exceptions.ConfargWarning)
    """

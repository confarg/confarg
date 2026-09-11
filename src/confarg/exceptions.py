# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exception and warning classes."""

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

    @classmethod
    def locals_not_self_describing(cls, locals_key: str, path: str) -> InvalidConfigFileError:
        """Return an error for a local variable loaded from a format that carries no types."""
        return cls(
            f"Local variable {path!r} came from a data file (.csv/.tsv), whose cells are untyped strings."
            f" The {locals_key!r} namespace has no type annotations to coerce against, so it accepts only"
            f" self-describing formats: .yaml/.yml, .toml, .json.",
        )

    @classmethod
    def ragged_csv_row(cls, path: Any, row_num: int, expected: int, got: int) -> InvalidConfigFileError:
        """Return an error for a CSV row whose cell count does not match the header/first row."""
        return cls(f"Ragged CSV row {row_num} in {path}: expected {expected} cells, got {got}")

    @classmethod
    def duplicate_csv_columns(cls, path: Any, names: list[str]) -> InvalidConfigFileError:
        """Return an error for a CSV header row that repeats a column name."""
        listed = ", ".join(repr(n) for n in names)
        return cls(f"Duplicate CSV column name(s) in {path}: {listed}")


class UnknownArgumentError(ConfargError):
    """Raised when an unrecognized CLI argument is encountered."""


class LocalsError(ConfargError):
    """Raised for misuse of the reserved local-variables namespace.

    Local variables may only be *declared* in a self-describing configuration file
    (YAML, TOML, JSON), which fixes their type; they may be *modified* from any
    channel, but only to a value of that type. Setting an undeclared local, adding or
    removing one from the environment or command line, or declaring the same
    namespace under both ``locals`` and ``_locals`` raises this error.

    Agent Notes:
        architecture/08-locals.md
    """

    @classmethod
    def ambiguous(cls, keys: list[str], where: str = "") -> LocalsError:
        """Return an error for local variables declared under more than one spelling."""
        listed = " and ".join(repr(k) for k in keys)
        at = f" under {where!r}" if where else ""
        return cls(
            f"Local variables are declared{at} under both {listed}, so which block holds them"
            f" is ambiguous. Use one spelling: {keys[0]!r} normally, or {keys[-1]!r} when the"
            f" configuration class has a field of the other name.",
        )

    @classmethod
    def not_assignable(cls, locals_key: str, config_flag: str, source: str) -> LocalsError:
        """Return an error for an attempt to replace the whole namespace from env or CLI."""
        hint = f" or declare a new set with --{config_flag}.{locals_key} FILE." if config_flag else "."
        return cls(
            f"The {locals_key!r} namespace cannot be assigned as a whole from the {source}."
            f" Modify one variable at a time ({locals_key}.<name>){hint}",
        )

    @classmethod
    def not_restructurable(cls, path: str, locals_key: str, source: str) -> LocalsError:
        """Return an error for an attempt to add or remove a local from env or CLI."""
        return cls(
            f"Local variable '{locals_key}.{path}' cannot be added or removed from the {source}:"
            f" which locals exist is owned by the configuration files that declare them."
            f" Change its value instead, or edit the declaring file.",
        )

    @classmethod
    def not_declared(cls, path: str, locals_key: str, config_flag: str, source: str) -> LocalsError:
        """Return an error for an override of a local variable no config file declared."""
        hint = (
            f" Declare it in a configuration file, or add one with --{config_flag}.{locals_key} FILE."
            if config_flag
            else " Declare it in a configuration file first."
        )
        return cls(
            f"Local variable '{locals_key}.{path}' is set on the {source} but declared by no configuration file.{hint}",
        )


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

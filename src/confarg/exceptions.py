# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exception and warning classes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


def _locals_file_flag(config_flag: str, locals_key: str) -> str | None:
    """Return the ``--<config_flag>.<locals_key> FILE`` flag, or None when there is no flag.

    ``config_flag=""`` suppresses the config-file flag, and then no message may offer it.
    """
    return f"--{config_flag}.{locals_key} FILE" if config_flag else None


class ConfargError(Exception):
    """Base exception for all confarg errors."""

    @classmethod
    def missing_value(cls, token: str, usage: str = "<value>") -> ConfargError:
        """Return the error for a value-taking flag that argv left without its value.

        The one spelling of the message, for the six sites that raise it: every
        value-consuming branch of the vanilla parser, and the adapters' own check for a
        multi-token flag the framework never saw. *usage* names the shape the flag wants
        when it is not a plain value -- ``'<json>'`` for a JSON cast.

        Dev Notes:
            docs-dev/architecture/10-design-decisions.md#a-whole-value-flag-needs-its-value
        """
        return cls(f"Missing value for {token!r}. Usage: {token} {usage}")

    @classmethod
    def root_cast_not_object(cls, flag: str, value: Any) -> ConfargError:
        """Return an error for a whole-configuration JSON cast that decoded to a non-mapping.

        Spelled once for the three channels that accept one -- ``--json``, ``<PREFIX>_JSON``
        and the adapters' flat ``json`` entry -- which differ only in how *flag* is written.
        *value* is always JSON the cast just decoded, so it is never a channel token and
        ``type()`` names it correctly on its own.
        """
        return cls(f"{flag} for a structured target must be a JSON object, got {type(value).__name__}.")

    @classmethod
    def include_siblings_need_a_dict(cls, include_key: str, included: Any) -> ConfargError:
        """Return an error for sibling keys beside an include that produced a non-mapping."""
        return cls(
            f"{include_key} produced {type(included).__name__} but sibling keys are"
            f" also present; can only merge sibling keys into a dict include",
        )


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
    def non_dict_root(cls, path: Any, value: Any) -> InvalidConfigFileError:
        """Return an error for a root config file whose top-level value is not a mapping."""
        return cls(
            f"Root config file must be a mapping, got {type(value).__name__}: {path}."
            f" A list or scalar top level is one value rather than a configuration layer, so it"
            f" is meaningful at a mounted node -- __include__, --config.<subpath> or"
            f" CONFIG__<SUBPATH> -- but not at the root of a configuration.",
        )

    @classmethod
    def unreachable(cls, loc: Any, exc: Any) -> InvalidConfigFileError:
        """Return an error for a config location whose scheme handler could not read it."""
        return cls(f"Cannot read config source {loc}: {exc}")

    @classmethod
    def unknown_scheme(cls, scheme: str, known: list[str]) -> InvalidConfigFileError:
        """Return an error for a location naming a scheme no handler is registered for."""
        listed = ", ".join(sorted(known))
        return cls(
            f"No handler registered for config source scheme {scheme + '://'!r}."
            f" Registered schemes: {listed}. Add one with confarg.register_scheme({scheme!r}, ...)."
            f" If you meant a local file whose name contains a colon, write it as ./{scheme}:...",
        )

    @classmethod
    def no_format(cls, loc: Any) -> InvalidConfigFileError:
        """Return an error for a location carrying no file extension to dispatch on."""
        return cls(
            f"Cannot tell the format of {loc}: it has no file extension."
            f" confarg chooses the parser by extension (.yaml/.yml, .toml, .json) and does not"
            f" inspect content or a Content-Type header.",
        )

    @classmethod
    def cross_origin_include(cls, base: Any, target: Any) -> InvalidConfigFileError:
        """Return an error for a remote document including a location outside its own origin."""
        return cls(
            f"Config source {base} may not include {target}: a document loaded over the network"
            f" can only include locations on its own scheme and host. Move the file next to it,"
            f" or name it from a local configuration file instead.",
        )

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

    @classmethod
    def no_such_field(cls, token: str, path: Sequence[str]) -> UnknownArgumentError:
        """Return an error for a flag whose dotted path names no field of the target."""
        return cls(f"Unknown argument: {token!r} (field '{'.'.join(path)}' not found)")

    @classmethod
    def not_indexable(cls, token: str, path: Sequence[str]) -> UnknownArgumentError:
        """Return an error for an index patch on a path that is not a list or dict."""
        return cls(f"Unknown argument: {token!r} (field '{'.'.join(path)}' not found or not indexable)")

    @classmethod
    def wrong_prefix(cls, token: str, cli_prefix: str) -> UnknownArgumentError:
        """Return an error for a flag that does not carry the required ``cli_prefix``."""
        return cls(f"Unknown argument: {token!r}. Expected arguments to start with --{cli_prefix}.")

    @classmethod
    def unexpected_positional(cls, token: str) -> UnknownArgumentError:
        """Return an error for an argv token no flag consumed.

        Raised wherever a token run ends before argv does: by the vanilla scan when it
        meets a bare word, and by the adapters when a fixed-arity flag was handed more
        tokens than its arity takes -- the same surplus, named the same way.
        """
        return cls(
            f"Unexpected positional argument: {token!r}. All arguments must be named flags (e.g. --fieldname value).",
        )


class LocalsError(ConfargError):
    """Raised for misuse of the reserved local-variables namespace.

    Local variables may only be *declared* in a self-describing configuration file
    (YAML, TOML, JSON), which fixes their type; they may be *modified* from any
    channel, but only to a value of that type. Setting an undeclared local, adding or
    removing one from the environment or command line, or declaring the same
    namespace under both ``locals`` and ``_locals`` raises this error.

    Dev Notes:
        docs-dev/architecture/08-locals.md
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
        flag = _locals_file_flag(config_flag, locals_key)
        hint = f" or declare a new set with {flag}." if flag else "."
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
        flag = _locals_file_flag(config_flag, locals_key)
        hint = (
            f" Declare it in a configuration file, or add one with {flag}."
            if flag
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

    @classmethod
    def anchor_above_root(cls, path: str, dots: int, scope: str = "document") -> MissingReferenceError:
        """Return an error for a relative reference that climbs past the root of its scope."""
        depth = len(path.split(".")) if path else 0
        where = f"'{path}'" if path else "the root"
        return cls(
            f"Relative reference '{'.' * dots}' at {where} climbs {dots} level(s) from a depth"
            f" of {depth}, above the {scope} root; use '::' for the configuration root",
        )


class UnsafeExpressionError(ConfargError):
    """Raised when an expression contains disallowed AST nodes or function calls."""


class ExpressionEvalError(ConfargError):
    """Raised for runtime errors during expression evaluation."""


class ConfargWarning(UserWarning):
    """Emitted for non-fatal configuration issues.

    Currently raised when an environment variable matches the configured prefix
    but does not correspond to any known field on the target type, and when
    dynamic CLI flag registration fails (the flags are skipped, not the parse).
    Convert to errors in your test-suite via::

        warnings.filterwarnings("error", category=confarg.exceptions.ConfargWarning)
    """

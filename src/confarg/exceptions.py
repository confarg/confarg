# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exception and warning classes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Sequence

#: How many characters of an overflowing number a warning shows before eliding the rest.
_SHOWN_DIGITS = 20


def _locals_file_flag(config_flag: str, locals_key: str) -> str | None:
    """Return the ``--<config_flag>.<locals_key> FILE`` flag, or None when there is no flag.

    ``config_flag=""`` suppresses the config-file flag, and then no message may offer it.
    """
    return f"--{config_flag}.{locals_key} FILE" if config_flag else None


FieldPath = tuple[str | int, ...]
"""A position below the target, one segment per step: a field or dict key by name, a sequence element by index."""


def _spell_field_path(path: FieldPath) -> str:
    """Spell *path* as a message names a field: each key after a dot, each index in brackets.

    ``("items", 0, "size")`` is ``items[0].size``; ``()``, the target itself, is ``""``.

    Dev Notes:
        docs-dev/architecture/types/construction.md#a-construction-path-is-a-sequence-of-segments
    """
    spelled = ""
    for segment in path:
        if isinstance(segment, int):
            spelled += f"[{segment}]"
        else:
            spelled += f".{segment}" if spelled else segment
    return spelled


def _append_none_remedy(message: str) -> str:
    """Return *message* followed by the remedy for a field whose ``None`` a channel spells as a none word."""
    return f"{message.removesuffix('.')}. To set this field to None, pass 'none' or 'null'."


def _in_expression(expression: str, reason: object) -> str:
    """Return the text of an expression's refusal or runtime failure: the expression as written, then why.

    *expression* is the ``${...}`` as written, the whole value for a pure expression and the
    fragment alone for one inside an interpolation; *reason* is what was refused, or
    Python's own exception for a runtime failure.

    Dev Notes:
        docs-dev/architecture/expressions/resolution.md#an-evaluation-failure-names-its-expression
        docs-dev/architecture/expressions/resolution.md#a-refusal-names-its-expression
    """
    return f"Error in expression {expression!r}: {reason}"


def _failure_text(exc: BaseException) -> str:
    """Return the text of Python's *exc* as an expression's failure gives it: its own, when it names a cause.

    An exception whose arguments are no one string, and that keeps ``BaseException``'s
    ``str()``, reads as the repr of its arguments: a ``decimal`` signal as the list of signal
    classes it raised, a float overflow as an errno tuple. Such an exception is named instead,
    module-qualified outside the builtins, followed by its string arguments and, in
    parentheses, the signal classes it lists besides its own: ``decimal.InvalidOperation
    (DivisionUndefined)``, ``OverflowError: Result too large`` (the C library's ``strerror``
    text, which varies by platform).

    Dev Notes:
        docs-dev/architecture/expressions/resolution.md#a-failure-whose-text-names-no-cause-names-its-exception
    """
    tp = type(exc)
    if tp.__str__ is not BaseException.__str__ or (len(exc.args) == 1 and isinstance(exc.args[0], str)):
        return str(exc)
    name = tp.__qualname__ if tp.__module__ == "builtins" else f"{tp.__module__}.{tp.__qualname__}"
    texts = [arg for arg in exc.args if isinstance(arg, str)]
    listed = [item for arg in exc.args if isinstance(arg, list | tuple) for item in arg]
    signals = [s.__qualname__ for s in listed if isinstance(s, type) and issubclass(s, BaseException) and s is not tp]
    return name + (f": {'; '.join(texts)}" if texts else "") + (f" ({', '.join(signals)})" if signals else "")


class ConfargError(Exception):
    """Base exception for all confarg errors."""

    def _with_none_remedy(self) -> Self:
        """Return an error of this type whose message ends with the none-word remedy.

        For an optional field that failed on a channel token: the error its one variant raised,
        and how to set the field to ``None`` instead.

        Dev Notes:
            docs-dev/architecture/types/construction.md#an-optional-field-fails-as-its-variant
        """
        return type(self)(_append_none_remedy(str(self)))

    @classmethod
    def missing_value(cls, token: str, usage: str = "<value>") -> ConfargError:
        """Return the error for a value-taking flag that argv left without its value.

        The one spelling of the message, for the six sites that raise it: every
        value-consuming branch of the vanilla parser, and the adapters' own check for a
        multi-token flag the framework never saw. *usage* names the shape the flag wants
        when it is not a plain value -- ``'<json>'`` for a JSON cast.

        Dev Notes:
            docs-dev/architecture/design-decisions/a-whole-value-flag-needs-its-value.md#a-whole-value-flag-needs-its-value
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
    def reserved_data_key(cls, key: str, path: str) -> ConfargError:
        """Return the error for a dict key ``dump()`` would write that a file reads as its own.

        *path* is the key's construction path, spelled; the key ends it.

        Dev Notes:
            docs-dev/architecture/config-files/reserved-keys.md#reserved-file-only-keys
        """
        return cls(
            f"Cannot dump the key {key!r} at '{path}': confarg reserves it, so a configuration file"
            " would read it as its own rather than as data.",
        )

    @classmethod
    def include_siblings_need_a_dict(cls, include_key: str, included: Any) -> ConfargError:
        """Return an error for sibling keys beside an include that produced a non-mapping."""
        return cls(
            f"{include_key} produced {type(included).__name__} but sibling keys are"
            f" also present; can only merge sibling keys into a dict include",
        )

    @classmethod
    def no_such_mount_point(cls, spelling: str, owner: str, valid: Sequence[str] | None) -> ConfargError:
        """Return the error for a mount flag whose subpath names no field of the target.

        The one spelling for the sites that intercept a mount flag — vanilla's scan, the
        adapters' rescan and the environment's config handler — which differ only in
        *spelling*: ``--config.dbb`` on argv, ``CONFARG_CONFIG__DBB`` in the environment.
        *valid* lists the field names the subpath could have named, or ``None`` when the node
        it descends to holds none.
        """
        if valid is None:
            return cls(f"{spelling} names no field of {owner} to mount a config file at: it holds no nested fields.")
        return cls(f"{spelling} names no field of {owner} to mount a config file at. Valid fields: {list(valid)}.")

    @classmethod
    def mount_below_a_value_root(cls, spelling: str, owner: str, root_key: str) -> ConfargError:
        """Return the error for a mount flag whose subpath reaches into a non-struct root's value.

        Such a root is set whole, from *root_key*, so no subpath of it is a mount point,
        whatever its type would hold there.
        """
        return cls(
            f"{spelling} mounts a config file below the {owner} root, which is set whole: "
            f"write its value under {root_key!r} in a root config file instead.",
        )

    @classmethod
    def reserved_key(cls, spelling: str, key: str) -> ConfargError:
        """Return the error for a flag, a variable or a mount point naming a key confarg reserves.

        The one spelling for the CLI's loop, the environment and the mount check, which differ
        only in *spelling*: ``--d.__base__``, ``APP_d.__base__``, ``--config.d.__base__``.

        Dev Notes:
            docs-dev/architecture/config-files/reserved-keys.md#reserved-file-only-keys
        """
        return cls(
            f"Cannot set {spelling!r}: {key!r} is a key confarg reserves, which only a configuration file may write.",
        )

    @classmethod
    def callable_not_spelled(cls, value: Any, reason: str) -> ConfargError:
        """Return the error for a callable ``dump()`` refuses, since no configuration spells it.

        The one spelling for a callable whose dotted path does not read back and for one with
        no path at all, which differ only in *reason*. *value* is the callable itself, never a
        channel token.

        Dev Notes:
            docs-dev/architecture/callables.md#round-trip
        """
        return cls(
            f"Cannot serialize callable {value!r}: no configuration spells it, since {reason}."
            " Dump the merged configuration instead, which keeps the spec that produced it.",
        )


class MissingFieldError(ConfargError):
    """Raised when a required field is not provided by any source.

    The message is spelled when the error is shown rather than when it is raised: its remedy
    names the CLI flag that sets the field, and every flag lives under the ``cli_prefix`` only
    the front-end that parsed the command line knows. :func:`confarg.load` and the adapters'
    ``from_*`` spell it under theirs; :func:`confarg.build` is given none.

    Dev Notes:
        docs-dev/architecture/types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it
    """

    def __init__(self, path: FieldPath, field_type: Any) -> None:
        """Record the field of type *field_type* at construction path *path*; ``()`` is the target itself."""
        super().__init__(path, field_type)
        self._path = path
        self._field_type = field_type
        self._cli_prefix = ""
        self._in_root_value = False
        self._none_remedy = False

    def __str__(self) -> str:
        """Return the message, its remedy naming the flag the CLI accepts under ``_cli_prefix``.

        The field is named as every construction message names it (``items[0].size``); its
        flag writes each segment of the path as one dotted CLI segment, an index included, so
        it names ``--items.0.size``, and a dict key spelled ``x[0]`` stays ``--d.x[0].size``.
        A field inside a non-struct target's value (``_in_root_value``) has no flag of its
        own, so it names the root ``json`` cast that sets the whole value. The target itself
        is set by the bare ``--<prefix>``, or, with no prefix, by the root ``json`` cast alone.
        """
        # Imported here: confarg._cast imports this module.
        from confarg._cast import JSON_CAST_NAME  # noqa: PLC0415

        if self._path:
            segments = (JSON_CAST_NAME,) if self._in_root_value else self._path
            flag = ".".join(str(segment) for segment in segments)
            flag = f"{self._cli_prefix}.{flag}" if self._cli_prefix else flag
            usage = f"--{flag} <json>" if self._in_root_value else f"--{flag}"
            message = (
                f"Missing required field '{_spell_field_path(self._path)}' of type {self._field_type!r}. "
                f"Set it via CLI ({usage}), environment variable, or config file."
            )
        else:
            usage = f"--{self._cli_prefix} <value>" if self._cli_prefix else f"--{JSON_CAST_NAME} <json>"
            message = (
                f"No value provided for target type {self._field_type!r}."
                f" Provide a value via CLI flag ({usage}), environment variable, or config file."
            )
        return _append_none_remedy(message) if self._none_remedy else message

    def _with_none_remedy(self) -> Self:
        """Return this error with the none-word remedy after its message, still spelled when shown."""
        error = type(self)(self._path, self._field_type)
        error._none_remedy = True
        return error


class SymbolImportError(ConfargError):
    """Raised when a dotted import path cannot be resolved.

    Distinct from :class:`TypeCoercionError` because the problem is with the
    import path itself (typo, missing module, attribute not found), not with a
    value that failed type conversion.
    """


class SymbolNotFoundError(SymbolImportError):
    """Raised when nothing answers to a dotted import path: no such module or attribute, or no path at all.

    A :class:`SymbolImportError` that is *not* this subclass comes from a module that does exist
    but fails while it is imported, a broken dependency or a circular import, as
    ``ModuleNotFoundError`` is the ``ImportError`` that says a module is absent.

    Dev Notes:
        docs-dev/architecture/types/dotted-imports.md#a-path-names-nothing-or-a-module-fails
    """


class TypeCoercionError(ConfargError):
    """Raised when a value cannot be coerced to the target type."""

    @classmethod
    def cannot_coerce(
        cls,
        src: str,
        value: Any,
        tp: str,
        path: str,
        *,
        none_sentinel: bool = False,
    ) -> TypeCoercionError:
        """Return an error for a value that cannot be coerced to the target type.

        *none_sentinel* appends the remedy for a union field whose ``None`` a channel spells
        as a none word, offered only when *value* is a token and the union counts ``None``
        among its variants: anywhere else the remedy would ask for the value just refused.
        """
        msg = f"Cannot coerce {src} {value!r} to {tp} at '{path}'"
        return cls(_append_none_remedy(msg) if none_sentinel else msg)

    @classmethod
    def cannot_coerce_to_union(  # noqa: PLR0913  # cannot_coerce's arguments, and the branches skipped
        cls,
        src: str,
        value: Any,
        tp: str,
        path: str,
        *,
        unread: Sequence[str] = (),
        none_sentinel: bool = False,
    ) -> TypeCoercionError:
        """Return :meth:`cannot_coerce`'s error for a union, naming the branches *unread* that read no value.

        A branch confarg reads nothing as is skipped, so the refusal says why no value could
        reach it, ahead of the none remedy :meth:`cannot_coerce` offers.
        """
        msg = f"Cannot coerce {src} {value!r} to {tp} at '{path}'"
        if unread:
            names = " and ".join(unread)
            msg += f"; {names} {'is no leaf type' if len(unread) == 1 else 'are no leaf types'} confarg reads"
        return cls(_append_none_remedy(msg) if none_sentinel else msg)

    @classmethod
    def subclass_refuses(cls, name: str, builtin: str, path: str, reason: str) -> TypeCoercionError:
        """Return the error for the subclass *name* of *builtin*, whose constructor takes no such value."""
        return cls(
            f"{name} at '{path}' does not take a {builtin}: {reason};"
            f" confarg.register_leaf_type({name}, ...) reads it another way",
        )

    @classmethod
    def forbidden_literal_member(cls, literal: str, member: Any, path: str) -> TypeCoercionError:
        """Return the error for a ``Literal`` holding *member*, which PEP 586 forbids, *literal* spelling it whole."""
        return cls(
            f"Invalid annotation {literal} at '{path}': its member {member!r} is a {type(member).__name__};"
            " a Literal member is an int, str, bytes, bool, Enum member or None (PEP 586)",
        )

    @classmethod
    def cannot_coerce_because(cls, src: str, value: Any, tp: str, path: str, hint: str) -> TypeCoercionError:
        """Return :meth:`cannot_coerce`'s error followed by *hint*, what the type reads, after a colon."""
        return cls(f"{cls.cannot_coerce(src, value, tp, path)}: {hint}")

    @classmethod
    def wrong_shape(cls, src: str, value: Any, what: str, accepted: str, path: str) -> TypeCoercionError:
        """Return the error for raw data no constructor of *what* accepts on shape.

        The one spelling for every shape refusal in construction, the sites differing only in
        *what* is being built and the *accepted* shapes. *src* is the value's type as text —
        ``_src_type(value)`` — passed in rather than computed, this module importing nothing
        from ``confarg``.

        Dev Notes:
            docs-dev/architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it
        """
        return cls(f"Cannot construct {what} at '{path}': expected {accepted}, got {src} {value!r}")

    @classmethod
    def unknown_fields(cls, names: Any, what: str, path: str, valid: list[str]) -> TypeCoercionError:
        """Return the error for keys a struct or a namedtuple declares no field for.

        *names* are the refused keys, listed sorted by the text a file spells them with (a YAML
        integer key, a pending list op), so keys of different types sort together; *valid* is
        the field list as the caller orders it.

        Dev Notes:
            docs-dev/architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it
        """
        return cls(
            f"Unknown field(s) {sorted(str(name) for name in names)} for {what} at '{path}'. Valid fields: {valid}"
        )

    @classmethod
    def cast_not_held(cls, cast: str, field: str, path: str) -> TypeCoercionError:
        """Return the error for a cast whose type the field's type does not hold.

        The one refusal for a pin that would place a value the field does not accept.
        *cast* names the pinned type and *field* the field's type, both spelled by the
        caller — this module importing nothing from ``confarg``.

        Dev Notes:
            docs-dev/architecture/design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds
        """
        return cls(
            f"Cannot cast to {cast} at '{path}': the field's type {field} does not hold it."
            " A cast names one of the types the field itself holds.",
        )

    @classmethod
    def op_not_a_list(cls, key: str, what: str, src: str, value: Any, path: str) -> TypeCoercionError:
        """Return the error for a list op whose key holds no list: the base, or the indices a delete reads.

        *key* is the reserved key a file writes the op with; *what* is what it must hold.
        *src* is the value's type as text, passed in rather than computed, this module
        importing nothing from ``confarg``; the value is never a token, as only a file writes
        the key.
        """
        return cls(f"Cannot patch the list at '{path}': {key!r} must hold {what}, got {src} {value!r}")

    @classmethod
    def index_unset(cls, unset_key: str, delete_key: str, index: Any, path: str) -> TypeCoercionError:
        """Return the error for an index of a list whose patch is a bare node delete.

        A file's ``"N": {__unset__: true}`` would leave nothing in the slot; the list deletes an
        index by *delete_key*. The keys are passed in, this module importing nothing from
        ``confarg``.

        Dev Notes:
            docs-dev/architecture/design-decisions/a-file-spells-an-op-in-its-value.md#where-a-delete-has-no-meaning
        """
        return cls(
            f"Cannot patch the list at '{path}': index {index} holds {unset_key!r} alone, which would"
            f" leave nothing in its place. A list deletes an index with {delete_key!r}: [{index}].",
        )

    @classmethod
    def position_list_delete(cls, key: str, unset_key: str, what: str, path: str) -> TypeCoercionError:
        """Return the error for a list delete (*key*) on a fixed-length sequence, which unsets a position in place.

        *what* names the type as the message reads it, a fixed tuple or a namedtuple; *unset_key*
        is the reserved key a file unsets a position with, passed in, this module importing
        nothing from ``confarg``.

        Dev Notes:
            docs-dev/architecture/design-decisions/a-fixed-length-delete-unsets-a-position.md#a-fixed-length-delete-unsets-a-position
        """
        return cls(
            f"Cannot apply {key!r} to the {what} at '{path}': a fixed-length sequence keeps its length,"
            f" so a position is unset in place rather than deleted. Write {{{unset_key}: true}} at the position:"
            f' {{"0": {{{unset_key}: true}}}}.',
        )

    @classmethod
    def list_op_on(cls, key: str, what: str, path: str) -> TypeCoercionError:
        """Return the error for a list op the merge recorded where the type has no list to apply it to.

        *key* is the reserved key a file writes the op with; *what* names the field's type
        as the message reads it: ``dict``, a fixed tuple, a namedtuple.
        """
        return cls(f"Cannot apply {key!r} to the {what} at '{path}': it is an operation on a list.")

    @classmethod
    def not_a_subclass(cls, name: Any, parent: str, path: str) -> TypeCoercionError:
        """Return the error for a class that is not a subclass of the target type.

        *name* arrives as the text the caller names the class by — a dotted name, or the
        string the user typed — and *parent* as a dotted name, both passed in rather than
        computed, this module importing nothing from ``confarg``.

        Dev Notes:
            docs-dev/architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it
        """
        return cls(f"Class {name!r} at '{path}' is not a subclass of {parent}.")

    @classmethod
    def refused_empty_call(cls, name: Any, path: str, reason: str, beside: str) -> TypeCoercionError:
        """Return the error for a class a tag or an opener named, refusing to be built with no arguments.

        *name* is the class as the user named it, *reason* Python's own text, and *beside* what
        the class's fields sit beside: the tag, or the opener that named it.

        Dev Notes:
            docs-dev/architecture/types/construction.md#a-class-built-from-nothing
        """
        return cls(
            f"Class {name!r} at '{path}' cannot be built with no arguments: {reason}."
            f" Supply the class's fields as keys beside the {beside}.",
        )

    @classmethod
    def tag_not_a_subclass(cls, name: Any, parent: str, path: str, call: str) -> TypeCoercionError:
        """Return the error for a class tag on a typed field that names no subclass of the field's type.

        *call* is the spelling of the ``call`` directive in the spec's mode, passed in because this
        module imports nothing from ``confarg``. The message names it to say what it does: it
        computes a value the field's type accepts, so it is no way to build the refused class.

        Dev Notes:
            docs-dev/architecture/design-decisions/class-names-a-subclass-call-computes.md#class-names-a-subclass-call-computes
        """
        return cls(
            f"Class {name!r} at '{path}' is not a subclass of {parent}."
            f" A '{call}:' spec computes a value the field's type accepts, so it cannot build this class either.",
        )


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
    def misplaced_unset(cls, unset_key: str, loc: Any, path: Sequence[str], reason: str) -> InvalidConfigFileError:
        """Return the error for a file's node delete written where it has no meaning.

        *unset_key* is the reserved key the file wrote, passed in because this module imports
        nothing from ``confarg``; *path* is the node's position in the document *loc*, one
        segment per key or list index, and *reason* says why no delete stands there.

        Dev Notes:
            docs-dev/architecture/design-decisions/a-file-spells-an-op-in-its-value.md#where-a-delete-has-no-meaning
        """
        where = f"'{'.'.join(path)}' in {loc}" if path else f"the root of {loc}"
        return cls(f"Cannot read {unset_key!r} at {where}: {reason}.")

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

    @classmethod
    def reserved_csv_columns(cls, path: Any, names: list[str]) -> InvalidConfigFileError:
        """Return an error for a CSV header row naming a key confarg reserves, where the names become keys.

        Dev Notes:
            docs-dev/architecture/config-files/reserved-keys.md#reserved-file-only-keys
        """
        listed = ", ".join(repr(n) for n in names)
        return cls(f"CSV column name(s) in {path} spell a key confarg reserves, which a data file cannot use: {listed}")


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
    def bare_prefix_on_struct_root(cls, token: str, cli_prefix: str) -> UnknownArgumentError:
        """Return an error for the bare prefix flag spelled against a struct-like root.

        The bare ``--<cli_prefix>`` flag is a scalar root's only CLI spelling; a
        struct-like root has fields to address instead, so the flag names nothing.
        """
        return cls(
            f"Unknown argument: {token!r}. The bare --{cli_prefix} flag carries a value only"
            f" for a scalar root; this target is structured. Address one of its fields"
            f" (--{cli_prefix}.<field>) instead.",
        )

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
        docs-dev/architecture/locals.md
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
    def uncalled(cls, path: str, kind: str, name: str, callee: str) -> MissingReferenceError:
        """Return an error for a missing field spelled like a whitelisted *kind* named without a call.

        *kind* is ``"function"`` or ``"method"``; *callee* is the text the call would put
        before ``(...)``.
        """
        return cls.field_not_found(path, f"'{name}' is a {kind} only when called, as in {callee}(...)")

    @classmethod
    def anchor_above_root(cls, path: str, depth: int, dots: int, scope: str = "document") -> MissingReferenceError:
        """Return an error for a relative reference that climbs past the root of its scope.

        *depth* is the number of segments in *path*, given apart because a key holding a dot
        makes the dotted *path* ambiguous to count.
        """
        where = f"'{path}'" if path else "the root"
        return cls(
            f"Relative reference '{'.' * dots}' at {where} climbs {dots} level(s) from a depth"
            f" of {depth}, above the {scope} root; use '::' for the configuration root",
        )


class UnsafeExpressionError(ConfargError):
    """Raised when an expression contains disallowed AST nodes or function calls."""

    @classmethod
    def refused(cls, expression: str, reason: str) -> UnsafeExpressionError:
        """Return the refusal of *expression*, as written, for *reason*."""
        return cls(_in_expression(expression, reason))


class ExpressionEvalError(ConfargError):
    """Raised for runtime errors during expression evaluation."""

    @classmethod
    def failed(cls, expression: str, exc: Exception) -> ExpressionEvalError:
        """Return the runtime failure of *expression*, as written, with Python's own *exc* as the reason."""
        return cls(_in_expression(expression, _failure_text(exc)))


class ConfargWarning(UserWarning):
    """Emitted for non-fatal configuration issues.

    Currently raised when an environment variable matches the configured prefix
    but does not correspond to any known field on the target type, when dynamic
    CLI flag registration fails (the flags are skipped, not the parse), when a
    dumped value will not read back as its own variant, when a tag-shaped
    key is a member's value at a position where a class-path tag could have
    dispatched, and when a number too large for a float reads as infinity
    (:class:`FloatOverflowWarning`). Convert to errors in your test-suite via::

        warnings.filterwarnings("error", category=confarg.exceptions.ConfargWarning)
    """

    @classmethod
    def tag_shadowed_by_member(cls, path: str, union_tag: str, what: str) -> ConfargWarning:
        """Return the warning for a tag-shaped key a member owns at a dispatch position.

        Emitted on use only, where a class-path tag was a real alternative, so the
        structural selection the member's value forces is never a surprise; *what*
        names what the fields select there ("variant" or "subclass"). The caller
        passes the display path (the root spelled as its own key), because this
        module imports nothing from confarg.

        Dev Notes:
            docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
        """
        return cls(
            f"The {union_tag!r} key at '{path}' is a field's value, not the tag:"
            " a member owns the tag's spelling there, so no class-path tag can dispatch"
            f" and the {what} is selected structurally. Rename the field or pass"
            " a different union_tag to keep the tag's spelling available.",
        )


class FloatOverflowWarning(ConfargWarning):
    """Emitted when a finite number too large for a float reads as infinity.

    A file's integer and a CLI or environment token are read as their digits read, so
    ``1e400`` and a 400-digit integer are ``inf`` on every channel; an infinity word
    (``inf``, ``-Infinity``) is meant and never warns. Cancel it alone via::

        warnings.filterwarnings("ignore", category=confarg.exceptions.FloatOverflowWarning)
    """

    @classmethod
    def at_path(cls, text: str, infinity: float, path: str) -> FloatOverflowWarning:
        """Return the warning for *text*, a finite number construction reads as *infinity* at *path*."""
        return cls(
            f"{_elided(text)} is too large for a float and reads as {infinity} at '{path}'."
            " Write inf to mean infinity.",
        )

    @classmethod
    def for_spelling(cls, text: str, infinity: float, spelling: str) -> FloatOverflowWarning:
        """Return the warning for *text*, a finite number the flag or variable *spelling* gives, read as *infinity*.

        A parser reads a token before the field's path is spelled, so the warning names
        what the user typed instead.
        """
        return cls(
            f"{_elided(text)} for {spelling} is too large for a float and reads as {infinity}."
            " Write inf to mean infinity.",
        )


def _elided(text: str) -> str:
    """Return *text*, cut after its first characters when an overflowing number is too long to show."""
    return text if len(text) <= _SHOWN_DIGITS else f"{text[:_SHOWN_DIGITS]}... ({len(text)} characters)"

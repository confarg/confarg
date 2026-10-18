# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Public API implementation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Unpack, cast, overload

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import UnionType
    from typing import TypeAliasType

from confarg import _defaults
from confarg._default_layer import drop_untouched, lay_defaults, settle_pending
from confarg._defaults import MergeOptions, _Options, _resolve_options
from confarg._files import _dump_file, _native_types_of
from confarg._merge import ListOp, MergeDict
from confarg._parse_cli import _config_pairs_in, _locals_keys_at, _parse_cli
from confarg._pipeline import _merge_sources
from confarg._serialize import _check_native_types, _DumpOptions, _serialize, _serialize_untyped, written_form
from confarg._typed_read import TypedReading
from confarg._types import _MISSING, TagPolicy, _is_struct_like, _resolve_type
from confarg.dictexpr import resolve_expressions
from confarg.exceptions import MissingFieldError
from confarg.typedload import construct as _tc
from confarg.typedload._coerce import _type_kind, _TypeKind
from confarg.typedload._construct import build_from_nothing


def merge(target: type | TypeAliasType | UnionType, **opts: Unpack[MergeOptions]) -> dict[str | ListOp, Any]:
    """Collect and merge configuration from all sources into a raw dict.

    Sources are merged in priority order: config files (lowest), then
    environment variables, then CLI arguments (highest). No expression
    resolution and no dataclass construction are performed — the returned
    dict reflects the config input exactly as written, with ${...}
    expression strings preserved.

    The returned dict is **unvalidated**: it is not guaranteed to be
    constructible into ``target``. Type validation and coercion happen in
    ``build()`` (or the one-shot ``load()``), which raises ``TypeCoercionError``
    / ``MissingFieldError`` for data that cannot be built. CLI parsing rejects
    only the cases it can prove wrong at parse time (e.g. a missing value); a
    config file or env var carrying ``"abc"`` for an ``int`` field merges
    cleanly here and fails later, in ``build()``.

    Args:
        target: The dataclass type (or scalar type) used to guide CLI parsing.
        **opts: The sources to read and how to read them; see :class:`MergeOptions`.

    Returns:
        A plain dict of the merged configuration, with expression strings intact. A list
        operation that only ``build()`` can apply stays in it, keyed by a
        :class:`confarg.ListOp`.

    Config file loading order:
        All config files share the same priority level (below inline env vars and
        CLI args).  Within that level they are loaded left-to-right so that later
        sources win on conflict.  The full sequence is:

        1. ``files`` — in the order given.
        2. ``env_config`` — the single global path named by that env var (if set).
        3. ``CONFIG__*`` env vars — sorted lexicographically by their env var name,
           which is equivalent to sorting by subpath depth (shallower paths first).
           A global ``CONFIG=file`` therefore loads before ``CONFIG__DB=db.yaml``,
           which loads before ``CONFIG__DB__HOST=host.yaml``.
        4. CLI ``--config`` / ``--config.subpath`` flags — in left-to-right order.

    Raises:
        InvalidConfigFileError: If a config file cannot be loaded.
        UnknownArgumentError: If an unrecognized CLI argument is encountered.
    """
    return _merge(target, _resolve_options("merge", opts))


def _merge(target: type | TypeAliasType | UnionType, options: _Options) -> MergeDict:
    """Merge every source into a raw dict; :func:`merge` with its options resolved."""
    prefix = _cli_prefix(options)

    def parse_cli(below: MergeDict) -> MergeDict:
        return _parse_cli(options.argv, target, prefix, options.config_flag, options.union_tag, below=below)[0]

    configs = _config_pairs_in(options.argv, target, prefix, options.config_flag, options.union_tag)
    return _merge_sources(target, parse_cli, configs, options)


def _cli_prefix(options: _Options) -> str:
    """Return the prefix vanilla's flags start with: omitted means the registered one, and vanilla registers none."""
    return "" if options.cli_prefix is None else options.cli_prefix


def _strip_locals(data: MergeDict, target: Any, union_tag: str) -> MergeDict:
    """Return *data* without the reserved local-variables namespaces, at every node.

    Never mutates *data*: nodes are copied only where a namespace is dropped, and
    returned as-is otherwise.

    Dev Notes:
        docs-dev/architecture/locals.md#stripping
    """
    return cast("MergeDict", _strip_locals_node(data, target, union_tag, []))


def _strip_locals_node(node: Any, target: Any, union_tag: str, path: list[str]) -> Any:
    """Strip every namespace at or below *node*, returning *node* itself if none."""
    if isinstance(node, list):
        stripped = [_strip_locals_node(v, target, union_tag, [*path, str(i)]) for i, v in enumerate(node)]
        return node if all(a is b for a, b in zip(stripped, node, strict=True)) else stripped
    if not isinstance(node, dict):
        return node
    drop = {key for key in _locals_keys_at(target, path, union_tag) if key in node}
    kept = {
        # An op build() applied no list for is no field: what it holds is not walked.
        k: v if isinstance(k, ListOp) else _strip_locals_node(v, target, union_tag, [*path, k])
        for k, v in node.items()
        if k not in drop
    }
    if not drop and all(kept[k] is v for k, v in node.items()):
        return node
    return kept


@overload
def build[T](target: type[T], data: dict[Any, Any], *, union_tag: str = ...) -> T: ...
@overload
def build(target: object, data: dict[Any, Any], *, union_tag: str = ...) -> Any: ...
def build[T](
    target: type[T] | TypeAliasType | UnionType,
    data: dict[Any, Any],
    *,
    union_tag: str = _defaults.UNION_TAG,
) -> T:
    """Resolve ``${...}`` expressions and construct the target type from a merged config dict.

    Use this as the second step after ``merge()``, or to load configuration
    from a dict you have assembled yourself.

    Args:
        target: The dataclass type (or scalar type) to construct.
        data: The raw config dict (e.g. the output of ``merge()``).
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        An instance of the target type.

    Raises:
        MissingFieldError: If a required field is not provided.
        TypeCoercionError: If a value cannot be coerced to the target type.
        AmbiguousUnionError: If a Union cannot be disambiguated.
        CircularReferenceError: If expression references form a cycle.
        UnsafeExpressionError: If an expression contains disallowed constructs.
        MissingReferenceError: If an expression references a field that does not exist.
        ExpressionEvalError: If an expression fails at runtime.
    """
    target_r = _resolve_type(target)
    resolved = _strip_locals(_resolve_over_defaults(target_r, data, union_tag), target_r, union_tag)
    return _construct_resolved(target_r, resolved, union_tag)


def _resolve_over_defaults(target_r: Any, data: MergeDict, union_tag: str) -> MergeDict:
    """Resolve *data*'s expressions over *target_r*'s field defaults, the defaults nobody touched taken out again.

    An expression reads an Enum or registered leaf as its object, and what it resolves to is
    left in its dump form.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer
        docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
    """
    laid = lay_defaults(target_r, data, union_tag, for_resolution=True)
    settle = settle_pending(target_r, union_tag)
    resolved = resolve_expressions(laid.data, read=TypedReading(target_r, union_tag), write=written_form, settle=settle)
    return drop_untouched(resolved, laid.untouched)


def _construct_resolved(target_r: Any, resolved: MergeDict, union_tag: str) -> Any:
    """Construct *target_r* from a resolved dict: a non-struct target from ``__root__``, a struct from the whole."""
    if not _is_struct_like(target_r):
        raw = resolved.get(_defaults.ROOT_KEY, _MISSING)
        if raw is _MISSING:
            raise MissingFieldError(path=(), field_type=target_r)
        try:
            return _tc(target_r, raw, union_tag=union_tag)
        except MissingFieldError as e:
            # Its remedy names the whole root's flag: no flag addresses a path below it.
            e._in_root_value = True
            raise
    if not resolved:
        # No channel supplied anything, so the root is built from {}: a guess a defaulted
        # field takes too, its refusal the missing root (BUG-184).
        return build_from_nothing(lambda: _tc(target_r, resolved, union_tag=union_tag), target_r, ())
    return _tc(target_r, resolved, union_tag=union_tag)


def _build_for_cli(target: Any, data: MergeDict, union_tag: str, cli_prefix: str) -> Any:
    """Return :func:`build`'s result, a ``MissingFieldError`` naming its flag under *cli_prefix*.

    The front-ends that parsed the command line build through it -- :func:`load` and the
    adapters' ``from_*`` -- since :func:`build` knows no prefix.

    Dev Notes:
        docs-dev/architecture/types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it
    """
    try:
        return build(target, data, union_tag=union_tag)
    except MissingFieldError as e:
        e._cli_prefix = cli_prefix
        raise


def resolve(
    target: type | TypeAliasType | UnionType,
    data: dict[Any, Any],
    *,
    union_tag: str = _defaults.UNION_TAG,
) -> dict[str | ListOp, Any]:
    """Resolve ``${...}`` expressions in a merged config dict, over the target's field defaults.

    Use this between ``merge()`` and ``from_dict()`` when you need the
    resolved dict itself (e.g. to inspect values or write it to a file):

        raw = confarg.merge(MyConfig, ...)
        resolved = confarg.resolve(MyConfig, raw)
        confarg.dump_file(resolved, "out.yaml")
        cfg = confarg.from_dict(MyConfig, resolved)

    The target's field defaults are the layer below *data*: an expression reads a default
    nobody set, and a patch the merge left pending over a defaulted field (``--t+ 3``) is
    applied over the default. A default nothing touched is not in the result; construction
    applies it.

    Args:
        target: The type *data* is for, whose field defaults lie below it; ``dict`` for none.
        data: A plain config dict, e.g. the output of ``merge()``.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        A new dict with all ``${...}`` expression strings replaced by their values.

    Raises:
        ConfargError: If a patch the merge left pending does not apply over a default.
        CircularReferenceError: If expression references form a cycle.
        UnsafeExpressionError: If an expression contains disallowed constructs.
        MissingReferenceError: If an expression references a field that does not exist.
        ExpressionEvalError: If an expression fails at runtime.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer
    """
    return _resolve_over_defaults(_resolve_type(target), data, union_tag)


@overload
def from_dict[T](target: type[T], data: dict[Any, Any], *, union_tag: str = ...) -> T: ...
@overload
def from_dict(target: object, data: dict[Any, Any], *, union_tag: str = ...) -> Any: ...
def from_dict[T](
    target: type[T] | TypeAliasType | UnionType,
    data: dict[Any, Any],
    *,
    union_tag: str = _defaults.UNION_TAG,
) -> T:
    """Construct a typed object from an already-resolved config dict.

    Unlike ``build()``, this does NOT resolve ``${...}`` expressions — call
    ``resolve()`` first if needed.

    Args:
        target: The dataclass or plain-class type to construct.
        data: A resolved config dict (output of resolve() or merge()).
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        An instance of the target type.

    Raises:
        MissingFieldError: If a required field is not provided.
        TypeCoercionError: If a value cannot be coerced to the target type.
        AmbiguousUnionError: If a Union cannot be disambiguated.
    """
    target_r = _resolve_type(target)
    laid = lay_defaults(target_r, data, union_tag, for_resolution=False).data
    return _construct_resolved(target_r, _strip_locals(laid, target_r, union_tag), union_tag)


@overload
def load[T](target: type[T], **opts: Unpack[MergeOptions]) -> T: ...
@overload
def load(target: object, **opts: Unpack[MergeOptions]) -> Any: ...
def load[T](target: type[T] | TypeAliasType | UnionType, **opts: Unpack[MergeOptions]) -> T:
    """Merge configuration from all sources and construct the target type.

    Convenience wrapper for ``merge()`` + ``build()``. For more control —
    e.g. to inspect or save the raw merged dict — call those directly.
    See ``merge()`` for source priority and config file loading order.

    Args:
        target: The dataclass type (or scalar type) to load configuration into.
        **opts: The sources to read and how to read them; see :class:`MergeOptions`.

    Returns:
        An instance of the target type populated with the merged configuration.

    Raises:
        MissingFieldError: If a required field is not provided by any source.
        TypeCoercionError: If a value cannot be coerced to the target type.
        InvalidConfigFileError: If a config file cannot be loaded.
        UnknownArgumentError: If an unrecognized CLI argument is encountered.
        AmbiguousUnionError: If a Union cannot be disambiguated.
        CircularReferenceError: If expression references form a cycle.
        UnsafeExpressionError: If an expression contains disallowed constructs.
        MissingReferenceError: If an expression references a field that does not exist.
        ExpressionEvalError: If an expression fails at runtime.
    """
    options = _resolve_options("load", opts)
    return _build_for_cli(target, _merge(target, options), options.union_tag, _cli_prefix(options))


def dump(
    value: Any,
    *,
    union_tag: str = _defaults.UNION_TAG,
    tag_policy: TagPolicy = "auto",
    native_types: Iterable[type] = (),
) -> dict[str, Any]:
    """Serialize a dataclass or plain-class instance to a config-compatible plain dict.

    The dump records the state the instance holds, not how it was produced:
    ``${...}`` expressions are written as their resolved values, and a value a ``call:``
    spec computed is written as that value, not as the call. A dataclass is written as the
    fields it stores, a field computed in ``__post_init__`` (``field(init=False)``)
    included and an ``InitVar`` left out, so such a dump records what the program ran with
    but does not load back as it stands. A plain class is written as its ``__init__``
    parameters, each read from the same-named attribute, property or slot the instance
    holds. To save a configuration as written, with its expressions and its ``call:``
    specs, pass the dict returned by ``merge()`` to ``dump_file()`` instead.

    A value of a registered leaf type — a ``Path``, a ``Decimal``, a ``date`` — is written as
    the text its type reads back, so the dict is ready for any writer, JSON's included.
    *native_types* keeps the values of the types it names as the objects they are, for a
    writer that holds them: ``confarg.dump(cfg, native_types=confarg.YAML_NATIVE_TYPES)``
    leaves each ``date`` and ``datetime`` a date. A value matches by its own type, so
    ``(date,)`` keeps a ``date`` and still writes a ``datetime`` as text; a datetime whose UTC
    offset has seconds, which no writer reads back, is always written as text.

    Args:
        value: A dataclass or plain-class instance.
        union_tag: The field name used as a discriminator tag in unions.
        tag_policy: ``"auto"`` (tag only when needed) or ``"always"`` (tag every union member).
        native_types: Registered leaf types written as the objects they are, not as text.

    Returns:
        A plain dict representation.

    Raises:
        TypeError: If value is not a dataclass or plain-class instance, or *native_types*
            names a type that is no registered leaf type.
        ConfargError: If the instance does not hold a field or a parameter it is dumped from.
    """
    if isinstance(value, dict):
        msg = (
            "dump() takes a dataclass or plain-class instance, not a dict."
            " To write a raw config dict to a file, use dump_file() directly."
        )
        raise TypeError(msg)
    if isinstance(value, type) or _type_kind(type(value)) is not _TypeKind.STRUCT:
        msg = f"Expected a dataclass or plain-class instance, got {type(value).__name__}"
        raise TypeError(msg)
    options = _DumpOptions(union_tag, tag_policy, _check_native_types(native_types))
    return _serialize(type(value), value, (), options)


def dump_file(
    value: Any,
    path: str | Path,
    *,
    union_tag: str = _defaults.UNION_TAG,
    tag_policy: TagPolicy = "auto",
    native_types: Iterable[type] | None = None,
) -> None:
    """Serialize and write to a config file.

    Accepts a dataclass or plain-class instance or a raw config dict (e.g. from ``merge()``
    or ``resolve()``). A dict is written as it stands, so the dict ``merge()``
    returns keeps its ``${...}`` expressions and ``call:`` specs; an instance is
    written as ``dump()`` serializes it, as the values it holds. The output
    format is determined by the file extension (.toml, .yaml, .yml, .json).

    A value of a registered leaf type is written as its text, except for the types the
    format holds natively: a YAML or a TOML file writes a ``date`` and a ``datetime`` as its
    own dates (``confarg.YAML_NATIVE_TYPES``, ``confarg.TOML_NATIVE_TYPES``), a JSON file
    none. *native_types* replaces that set, as :func:`dump`'s does.

    A TOML or a JSON file writes a dict key that is no string as its text, ``1`` as ``"1"`` and
    a date as its ISO text, which a typed dict reads back as the key it was. What the format
    does not hold is refused before the file is opened, which is then left as it was: an
    object no configuration spells, a ``None`` in TOML, which has no null, a key with no text,
    such as a tuple, or two keys of one dict written as the same text, ``1`` and ``"1"``.

    Args:
        value: A dataclass or plain-class instance, or a raw config dict.
        path: Path to the output file.
        union_tag: The field name used as a discriminator tag in unions.
        tag_policy: ``"auto"`` or ``"always"``.
        native_types: Registered leaf types written as the objects they are; None for the
            set the format holds natively.

    Raises:
        TypeError: If value is not a dataclass or plain-class instance, or a dict, or
            *native_types* names a type that is no registered leaf type.
        InvalidConfigFileError: If the format is unsupported or the required library is not installed.
        ConfargError: If *value* holds a value or a key the format does not hold, or :func:`dump`
            refuses it.
    """
    native = _native_types_of(Path(path)) if native_types is None else _check_native_types(native_types)
    if isinstance(value, dict):
        _dump_file(_serialize_untyped(value, native), Path(path))
    else:
        _dump_file(dump(value, union_tag=union_tag, tag_policy=tag_policy, native_types=native), Path(path))

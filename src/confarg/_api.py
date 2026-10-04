# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Public API implementation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Unpack, cast, overload

if TYPE_CHECKING:
    from types import UnionType
    from typing import TypeAliasType

from confarg import _defaults
from confarg._defaults import MergeOptions, _Options, _resolve_options
from confarg._files import _dump_file
from confarg._parse_cli import _locals_keys_at, _parse_cli
from confarg._pipeline import _merge_sources
from confarg._serialize import _serialize, _serialize_untyped
from confarg._types import _MISSING, TagPolicy, _is_dc, _is_struct, _is_struct_like, _resolve_type
from confarg.dictexpr import resolve_expressions
from confarg.exceptions import MissingFieldError
from confarg.typedload import construct as _tc


def merge(target: type | TypeAliasType | UnionType, **opts: Unpack[MergeOptions]) -> dict[str, Any]:
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
        A plain dict of the merged configuration, with expression strings intact.

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


def _merge(target: type | TypeAliasType | UnionType, options: _Options) -> dict[str, Any]:
    """Merge every source into a raw dict; :func:`merge` with its options resolved."""
    # Vanilla registers no flags, so omitting the prefix means the registered one: none.
    cli_prefix = "" if options.cli_prefix is None else options.cli_prefix
    cli_data, cli_configs = _parse_cli(options.argv, target, cli_prefix, options.config_flag, options.union_tag)
    return _merge_sources(target, cli_data, cli_configs, options)


def _strip_locals(data: dict[str, Any], target: Any, union_tag: str) -> dict[str, Any]:
    """Return *data* without the reserved local-variables namespaces, at every node.

    Never mutates *data*: nodes are copied only where a namespace is dropped, and
    returned as-is otherwise.

    Dev Notes:
        docs-dev/architecture/locals.md#stripping
    """
    return cast("dict[str, Any]", _strip_locals_node(data, target, union_tag, []))


def _strip_locals_node(node: Any, target: Any, union_tag: str, path: list[str]) -> Any:
    """Strip every namespace at or below *node*, returning *node* itself if none."""
    if isinstance(node, list):
        stripped = [_strip_locals_node(v, target, union_tag, [*path, str(i)]) for i, v in enumerate(node)]
        return node if all(a is b for a, b in zip(stripped, node, strict=True)) else stripped
    if not isinstance(node, dict):
        return node
    drop = {key for key in _locals_keys_at(target, path, union_tag) if key in node}
    kept = {k: _strip_locals_node(v, target, union_tag, [*path, k]) for k, v in node.items() if k not in drop}
    if not drop and all(kept[k] is v for k, v in node.items()):
        return node
    return kept


@overload
def build[T](target: type[T], data: dict[str, Any], *, union_tag: str = ...) -> T: ...
@overload
def build(target: object, data: dict[str, Any], *, union_tag: str = ...) -> Any: ...
def build[T](
    target: type[T] | TypeAliasType | UnionType,
    data: dict[str, Any],
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
    is_dataclass = _is_struct_like(target_r)

    resolved = _strip_locals(resolve_expressions(data), target_r, union_tag)

    if not is_dataclass:
        raw = resolved.get(_defaults.ROOT_KEY, _MISSING)
        if raw is _MISSING:
            msg = (
                f"No value provided for target type {target_r!r}."
                " Provide a value via CLI flag (--<prefix> <value>), environment variable, or config file."
            )
            raise MissingFieldError(msg)
        return _tc(target_r, raw, union_tag=union_tag)
    return _tc(target_r, resolved, union_tag=union_tag)


def resolve(data: dict[str, Any]) -> dict[str, Any]:
    """Resolve ``${...}`` expressions in a merged config dict.

    Use this between ``merge()`` and ``from_dict()`` when you need the
    resolved dict itself (e.g. to inspect values or write it to a file):

        raw = confarg.merge(MyConfig, ...)
        resolved = confarg.resolve(raw)
        confarg.dump_file(resolved, "out.yaml")
        cfg = confarg.from_dict(MyConfig, resolved)

    Args:
        data: A plain config dict, e.g. the output of ``merge()``.

    Returns:
        A new dict with all ``${...}`` expression strings replaced by their values.

    Raises:
        CircularReferenceError: If expression references form a cycle.
        UnsafeExpressionError: If an expression contains disallowed constructs.
        MissingReferenceError: If an expression references a field that does not exist.
        ExpressionEvalError: If an expression fails at runtime.
    """
    return resolve_expressions(data)


@overload
def from_dict[T](target: type[T], data: dict[str, Any], *, union_tag: str = ...) -> T: ...
@overload
def from_dict(target: object, data: dict[str, Any], *, union_tag: str = ...) -> Any: ...
def from_dict[T](
    target: type[T] | TypeAliasType | UnionType,
    data: dict[str, Any],
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
    return _tc(target_r, _strip_locals(data, target_r, union_tag), union_tag=union_tag)


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
    return build(target, _merge(target, options), union_tag=options.union_tag)


def dump(
    value: Any,
    *,
    union_tag: str = _defaults.UNION_TAG,
    tag_policy: TagPolicy = "auto",
) -> dict[str, Any]:
    """Serialize a dataclass instance to a config-compatible plain dict.

    The instance holds resolved values, so ``${...}`` expressions are not reproduced;
    to save a configuration with its expressions, pass the dict returned by
    ``merge()`` to ``dump_file()`` instead. Plain (non-dataclass) classes are not
    supported.

    Args:
        value: A dataclass instance.
        union_tag: The field name used as a discriminator tag in unions.
        tag_policy: ``"auto"`` (tag only when needed) or ``"always"`` (tag every union member).

    Returns:
        A plain dict representation.

    Raises:
        TypeError: If value is not a dataclass instance.
    """
    if isinstance(value, dict):
        msg = (
            "dump() takes a dataclass instance, not a dict."
            " To write a raw config dict to a file, use dump_file() directly."
        )
        raise TypeError(msg)
    if isinstance(value, type) or not _is_dc(type(value)):
        tp_name = type(value).__name__
        if _is_struct(type(value)):
            msg = (
                f"dump() only supports dataclass instances, not plain classes.\n"
                f"{tp_name} is a plain class — keep the merged dict and dump that instead:\n"
                f"  raw = confarg.merge(...)\n"
                f"  confarg.dump_file(raw, path)"
            )
            raise TypeError(msg)
        msg = f"Expected a dataclass instance, got {tp_name}"
        raise TypeError(msg)
    tp = type(value)
    return _serialize(tp, value, "", union_tag, tag_policy)


def dump_file(
    value: Any,
    path: str | Path,
    *,
    union_tag: str = _defaults.UNION_TAG,
    tag_policy: TagPolicy = "auto",
) -> None:
    """Serialize and write to a config file.

    Accepts a dataclass instance or a raw config dict (e.g. from ``merge()``
    or ``resolve()``). The output format is determined by the file extension
    (.toml, .yaml, .yml, .json).

    Args:
        value: A dataclass instance or a raw config dict.
        path: Path to the output file.
        union_tag: The field name used as a discriminator tag in unions.
        tag_policy: ``"auto"`` or ``"always"``.

    Raises:
        TypeError: If value is not a dataclass instance or a dict.
        InvalidConfigFileError: If the format is unsupported or the required library is not installed.
    """
    if isinstance(value, dict):
        _dump_file(_serialize_untyped(value), Path(path))
    else:
        _dump_file(dump(value, union_tag=union_tag, tag_policy=tag_policy), Path(path))

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The single source-merging pipeline shared by ``confarg.merge()`` and all CLI adapters.

Every entry point — vanilla :func:`confarg.merge` and the argparse/click/cyclopts
``merge_*`` functions — first extracts CLI-provided values and ``--config`` file
pairs in its own way, then delegates here for env parsing, config-file loading,
local-variable checks, the final ``config < env < CLI`` merge and reference
canonicalization.

Agent Notes:
    architecture/01-pipeline-and-contracts.md#the-single-merge-pipeline
    architecture/08-locals.md
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

from confarg._files import _load_file, _load_file_item, _load_subpath_files
from confarg._merge import (
    DICT_DELETE,
    LIST_DELETE_KEY,
    LIST_POST_APPEND_DELETE_KEY,
    LIST_REPLACE_BASE_KEY,
    _deep_merge,
)
from confarg._merge import LIST_APPEND_KEY as _LIST_APPEND_KEY
from confarg._parse_cli import _locals_keys, _locals_keys_at
from confarg._parse_env import _parse_env
from confarg._types import _StrToken
from confarg.dictexpr import contains_expression
from confarg.dictexpr._expressions import canonicalize_references, prefix_references
from confarg.exceptions import ConfargError, InvalidConfigFileError, LocalsError, TypeCoercionError
from confarg.typedload._coerce import _coerce_leaf


def _load_cli_config(fpath: Path, subpath: str, config_flag: str) -> dict[str, Any]:
    """Load one CLI config file (--config[.subpath][+] fpath) into a nested dict."""
    if subpath.endswith("+"):
        real_subpath = subpath[:-1].rstrip(".")
        if not real_subpath:
            msg = f"--{config_flag}+ requires a field path. Use --{config_flag}.fieldname+ /path/to/file."
            raise ConfargError(msg)
        last_key = real_subpath.rsplit(".", 1)[-1]
        fitem = _load_file_item(fpath)
        if isinstance(fitem, list):
            append_items: list[Any] = [fitem]
        elif isinstance(fitem, dict) and len(fitem) == 1 and last_key in fitem and isinstance(fitem[last_key], list):
            append_items = fitem[last_key]
        else:
            append_items = [fitem]
        fdata: dict[str, Any] = {_LIST_APPEND_KEY: append_items}
        for part in reversed(real_subpath.split(".")):
            fdata = {part: fdata}
        return fdata

    fdata = _load_file(fpath)
    if subpath:
        fdata = prefix_references(fdata, subpath)
        for part in reversed(subpath.split(".")):
            fdata = {part: fdata}
    return fdata


def _check_locals_are_typed(node: Any, locals_key: str, path: str) -> None:
    """Raise if any leaf under the local-variables namespace is an untyped string token.

    Such tokens come from data files (.csv/.tsv), by any route: ``files=``,
    ``__include__``, or ``--config.<key>[+]``.

    Agent Notes:
        architecture/08-locals.md#declare-in-files-modify-anywhere
    """
    if isinstance(node, _StrToken):
        raise InvalidConfigFileError.locals_not_self_describing(locals_key, path)
    if isinstance(node, dict):
        for k, v in node.items():
            _check_locals_are_typed(v, locals_key, f"{path}.{k}")
    elif isinstance(node, list | tuple):
        for i, item in enumerate(node):
            _check_locals_are_typed(item, locals_key, f"{path}.{i}")


_UNSET = object()

#: Keys ``_deep_merge`` reads as list append/delete/replace operations.
_MERGE_OP_KEYS = frozenset(
    {_LIST_APPEND_KEY, LIST_DELETE_KEY, LIST_POST_APPEND_DELETE_KEY, LIST_REPLACE_BASE_KEY},
)


def _lookup_declared(node: Any, path: list[str]) -> Any:
    """Return the declared value at *path*, or ``_UNSET`` if the path is not declared.

    Walks the config-file layer of the locals namespace the same way the value
    itself is nested: dict keys by name, list/tuple entries by integer index.
    """
    for part in path:
        if isinstance(node, dict):
            if part not in node:
                return _UNSET
            node = node[part]
        elif isinstance(node, list | tuple):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return _UNSET
        else:
            return _UNSET
    return node


def _coerce_override(value: Any, declared: Any, path: str) -> Any:
    """Coerce one env/CLI local-variable override to the runtime type of its declaration.

    Raises ``TypeCoercionError`` when the override cannot take the declared type, or
    when it swaps a container for a scalar (or the reverse). Expression tokens pass
    through untouched.

    Agent Notes:
        architecture/08-locals.md#declare-in-files-modify-anywhere
        architecture/07-expressions.md#deferral-rule
    """
    if contains_expression(value) or declared is None:
        return value
    declared_is_container = isinstance(declared, dict | list | tuple)
    value_is_container = isinstance(value, dict | list | tuple)
    if declared_is_container and value_is_container:
        return value  # whole-container replacement, e.g. from a `.json` cast
    if declared_is_container or value_is_container:
        got = type(value).__name__ if value_is_container else repr(str(value))
        msg = (
            f"Cannot set local variable {path!r} to {got}:"
            f" it is declared as a {type(declared).__name__}, and a local's type cannot change."
        )
        raise TypeCoercionError(msg)
    return _coerce_leaf(type(declared), value, path)


def _apply_locals_overrides(  # noqa: PLR0913  # recursive walk: carries both the declaration and the error context
    declared: Any,
    override: dict[str, Any],
    locals_key: str,
    config_flag: str,
    source: str,
    prefix: list[str] | None = None,
) -> None:
    """Check and coerce one source's local-variable overrides in place.

    *declared* is the config-file layer of the namespace. Raises ``LocalsError`` for an
    undeclared name, an add/remove operation, or a whole-namespace assignment.

    Agent Notes:
        architecture/08-locals.md#declare-in-files-modify-anywhere
    """
    if not isinstance(override, dict):
        raise LocalsError.not_assignable(locals_key, config_flag, source)
    prefix = prefix or []
    for key, value in override.items():
        path = [*prefix, key]
        # Merge-op markers would add or remove a local: refused with their own error.
        if value is DICT_DELETE or key in _MERGE_OP_KEYS:
            raise LocalsError.not_restructurable(".".join(prefix or path), locals_key, source)
        found = _lookup_declared(declared, path)
        if found is _UNSET:
            raise LocalsError.not_declared(".".join(path), locals_key, config_flag, source)
        # A list-index patch arrives as {"0": value}, so descend into a declared
        # sequence as well as a declared mapping.
        if isinstance(value, dict) and isinstance(found, dict | list | tuple):
            _apply_locals_overrides(declared, value, locals_key, config_flag, source, path)
        else:
            override[key] = _coerce_override(value, found, f"{locals_key}.{'.'.join(path)}")


def _lookup_path(data: Any, path: list[str]) -> Any:
    """Return the node at *path*, or ``None`` when the path is absent."""
    for part in path:
        if isinstance(data, dict):
            if part not in data:
                return None
            data = data[part]
        elif isinstance(data, list | tuple):
            try:
                data = data[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return data


def _iter_namespace_nodes(
    sources: list[Any],
    target: Any,
    union_tag: str,
    path: list[str] | None = None,
) -> Iterator[tuple[list[str], tuple[str, ...]]]:
    """Yield ``(path, keys)`` for each node that may hold a local-variables namespace.

    Walks the union of the key structures of all *sources* (not a merged result), so a
    namespace present in any single source is visited.

    Agent Notes:
        architecture/08-locals.md#declare-in-files-modify-anywhere
    """
    path = path or []
    dicts = [s for s in sources if isinstance(s, dict)]
    lists = [s for s in sources if isinstance(s, list)]
    keys = _locals_keys_at(target, path, union_tag) if dicts else ()
    if keys:
        yield path, keys
    if dicts:
        names: dict[str, None] = {}
        for d in dicts:
            for k in d:
                names.setdefault(k, None)
        for name in names:
            if name in keys:
                continue  # inside a namespace everything is free-form data
            yield from _iter_namespace_nodes([d.get(name) for d in dicts], target, union_tag, [*path, name])
    if lists:
        for i in range(max(len(x) for x in lists)):
            items = [x[i] for x in lists if i < len(x)]
            yield from _iter_namespace_nodes(items, target, union_tag, [*path, str(i)])


def _apply_locals_layer(  # noqa: PLR0913  # three source layers plus the two names they are read against
    target: Any,
    config_data: dict[str, Any],
    env_data: dict[str, Any],
    cli_data: dict[str, Any],
    *,
    union_tag: str,
    config_flag: str,
) -> None:
    """Validate and coerce every local-variables namespace across the three layers.

    *config_data* declares the locals; overrides in *env_data* and *cli_data* are
    checked against it and coerced in place. Namespaces are found at every node.

    Agent Notes:
        architecture/08-locals.md
    """
    for path, keys in _iter_namespace_nodes([config_data, env_data, cli_data], target, union_tag):
        node = _lookup_path(config_data, path)
        node = node if isinstance(node, dict) else {}
        declaring = [key for key in keys if key in node]
        if len(declaring) > 1:
            raise LocalsError.ambiguous(declaring, ".".join(path))
        for key in keys:
            where = ".".join([*path, key])
            if key in node:
                _check_locals_are_typed(node[key], where, where)
            declared = node.get(key, {})
            for source, source_data in (("environment", env_data), ("command line", cli_data)):
                sub = _lookup_path(source_data, path)
                if isinstance(sub, dict) and key in sub:
                    _apply_locals_overrides(declared, sub[key], where, config_flag, source)


def _merge_sources(  # noqa: PLR0913  # internal pipeline; mirrors merge()'s parameter surface
    target: Any,
    cli_data: dict[str, Any],
    cli_configs: Sequence[tuple[str, Path]],
    *,
    env: Mapping[str, str],
    env_prefix: str | None,
    env_separator: str,
    config_flag: str,
    files: Sequence[str | Path],
    env_config: str | None,
    union_tag: str,
) -> dict[str, Any]:
    """Merge pre-collected CLI data with env vars and config files in priority order.

    Args:
        target: The target type, guiding env-var parsing.
        cli_data: Nested dict of CLI-provided field values (highest priority).
        cli_configs: (subpath, path) pairs from ``--config[.subpath][+]`` flags,
            in left-to-right CLI order.
        env: Environment variable mapping to scan.
        env_prefix: Prefix that env vars must start with; ``None`` disables
            env-var parsing entirely.
        env_separator: Separator used to split env var names into nested keys.
        config_flag: Name of the config-file flag; the env segment with this name
            marks a sub-config file pointer. ``""`` disables env config pointers.
        files: Paths of config files to load first (lowest priority).
        env_config: Name of an env var whose value is a config file path to load
            after ``files`` but before env- and CLI-specified config files.
        union_tag: Field name used as a discriminator tag in union types.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Config file loading order (all at the same priority level, below inline
    env vars and CLI args; later files win on conflict):
        1. ``files`` — in the order given.
        2. ``env_config`` — the single global path named by that env var (if set).
        3. ``<config_flag>__*`` env vars — sorted lexicographically, i.e. by
           subpath depth (shallower paths first).
        4. ``cli_configs`` — in left-to-right CLI order.
    """
    locals_keys = _locals_keys(target, union_tag)
    if config_flag in locals_keys:
        msg = (
            f"config_flag is {config_flag!r}, which is also a name of the local-variables"
            f" namespace. The config-file flag is intercepted before field lookup, so"
            f" --{config_flag}.<name> could never reach a local variable."
            f" Pass a different config_flag to merge()/load(), e.g. config_flag='conf'."
        )
        raise ConfargError(msg)

    # 1. Parse env vars (done here so env-specified config files are loaded in order)
    if env_prefix is None:
        env_data: dict[str, Any] = {}
        env_configs: list[tuple[str, Path]] = []
    else:
        # Exclude the env_config key so it is not mistakenly treated as a field.
        env_for_fields = {k: v for k, v in env.items() if k != env_config} if env_config else env
        env_data, env_configs = _parse_env(
            env_for_fields,
            env_prefix,
            env_separator,
            target,
            config_flag,
            union_tag,
        )

    # 2. Load config files in priority order (all become config-level, below inline env/CLI)
    file_entries: list[tuple[str, Path]] = [("", Path(f)) for f in files]
    if env_config and (env_config_path := env.get(env_config)):
        file_entries.append(("", Path(env_config_path)))
    env_configs.sort(key=lambda ec: ec[0])
    config_data = _load_subpath_files(file_entries + env_configs, union_tag)
    for subpath, fpath in cli_configs:
        fdata = _load_cli_config(fpath, subpath, config_flag)
        config_data = _deep_merge(config_data, fdata, union_tag=union_tag)

    _apply_locals_layer(
        target,
        config_data,
        env_data,
        cli_data,
        union_tag=union_tag,
        config_flag=config_flag,
    )

    # 3. Merge: config (lowest) → env → CLI (highest)
    merged = _deep_merge(config_data, env_data, union_tag=union_tag)
    merged = _deep_merge(merged, cli_data, union_tag=union_tag)

    # Every file is mounted now: rewrite document-root references (${.x}) as plain paths.
    # See architecture/07-expressions.md#reference-anchoring.
    return canonicalize_references(merged)

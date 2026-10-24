# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The single source-merging pipeline shared by ``confarg.merge()`` and all CLI adapters.

Every entry point — vanilla :func:`confarg.merge` and the argparse/click/cyclopts
``merge_*`` functions — first extracts CLI-provided values and ``--config`` file
pairs in its own way, then delegates here for env parsing, config-file loading,
local-variable checks, the final ``config < env < CLI`` merge and reference
canonicalization.

Dev Notes:
    docs-dev/architecture/pipeline/merge-order.md#the-single-merge-pipeline
    docs-dev/architecture/locals.md
"""

from __future__ import annotations

import operator
import warnings
from itertools import chain
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from confarg._defaults import _Options

from confarg._depth import Copies
from confarg._files import _load_mount, _load_subpath_files
from confarg._merge import (
    _SHAPE,
    APPEND_SUFFIX,
    ListOp,
    MergeAt,
    MergeDict,
    _apply_list_ops,
    _deep_merge,
    _DeleteSentinel,
    _drop_deleted_bases,
    _resolve_index,
    _to_append_list,
)
from confarg._naming import names_something
from confarg._parse_cli import _locals_keys, _locals_keys_reached, _step_states, _walk_start, _WalkState
from confarg._parse_env import _env_config_pointers, _parse_env
from confarg._typed_merge import merge_root
from confarg._types import _StrToken
from confarg.dictexpr import contains_expression
from confarg.dictexpr._expressions import canonicalize_references
from confarg.exceptions import ConfargError, InvalidConfigFileError, LocalsError, TypeCoercionError
from confarg.typedload._coerce import _coerce_leaf


def _load_cli_config(value: Any, subpath: str, config_flag: str, root: MergeAt, *, copies: Copies) -> MergeDict:
    """Load one CLI config source (``--config[.subpath][+] VALUE``) into a nested dict.

    *value* is mounted at *subpath* by :func:`~confarg._files._load_mount`, the route every
    channel's mount takes, the ``+`` form appending. Only a ``+`` naming no field is the
    flag's own mistake, reported in its own spelling. *root*, where the merge stands at the
    configuration root, types the node each part merges at.

    Dev Notes:
        docs-dev/architecture/config-files/mounting.md#mounting
        docs-dev/architecture/design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel
    """
    if subpath.endswith(APPEND_SUFFIX):
        real_subpath = subpath[: -len(APPEND_SUFFIX)]
        if not real_subpath or real_subpath.endswith("."):
            msg = (
                f"--{config_flag}{'.' + real_subpath if real_subpath else ''}{APPEND_SUFFIX}"
                f" requires a field path to append to."
                f" Use --{config_flag}.fieldname{APPEND_SUFFIX} /path/to/file."
            )
            raise ConfargError(msg)
    return _load_mount(value, subpath, root=root, copies=copies)


def _check_locals_are_typed(node: Any, locals_key: str, path: str) -> None:
    """Raise if any leaf under the local-variables namespace is an untyped string token.

    Such tokens come from data files (.csv/.tsv), by any route: ``files=``,
    ``__include__``, or ``--config.<key>[+]``.

    Dev Notes:
        docs-dev/architecture/locals.md#declare-in-files-modify-anywhere
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

    Dev Notes:
        docs-dev/architecture/locals.md#declare-in-files-modify-anywhere
        docs-dev/architecture/expressions/deferral-rule.md#deferral-rule
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
            f" it is declared as {type(declared).__name__} {declared!r}, and a local's type cannot change."
        )
        raise TypeCoercionError(msg)
    return _coerce_leaf(type(declared), value, path)


def _apply_locals_overrides(  # noqa: PLR0913, PLR0917  # recursive walk: carries the declaration and the error context
    declared: Any,
    override: MergeDict,
    locals_key: str,
    config_flag: str,
    source: str,
    prefix: list[str] | None = None,
) -> None:
    """Check and coerce one source's local-variable overrides in place.

    *declared* is the config-file layer of the namespace. Raises ``LocalsError`` for an
    undeclared name, an add/remove operation, or a whole-namespace assignment.

    Dev Notes:
        docs-dev/architecture/locals.md#declare-in-files-modify-anywhere
    """
    if not isinstance(override, dict):
        raise LocalsError.not_assignable(locals_key, config_flag, source)
    prefix = prefix or []
    for key, value in override.items():
        # Merge-op markers would add or remove a local: refused with their own error. A delete
        # the root json fold kept spent is a delete too.
        if isinstance(value, _DeleteSentinel) or isinstance(key, ListOp):
            raise LocalsError.not_restructurable(".".join(prefix) or str(key), locals_key, source)
        path = [*prefix, key]
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
    states: list[_WalkState] | None = None,
) -> Iterator[tuple[list[str], tuple[str, ...]]]:
    """Yield ``(path, keys)`` for each node that may hold a local-variables namespace.

    Walks the union of the key structures of all *sources*, lowest first (not a merged
    result), so a namespace present in any single source is visited. A child is stepped to
    by the class the highest source naming its parent names: a higher layer's tag replaces
    the node below it, so it is the class every key the merge keeps there is built by.

    Dev Notes:
        docs-dev/architecture/locals.md#declare-in-files-modify-anywhere
    """
    path = path or []
    states = [_walk_start(target)] if states is None else states
    dicts = [s for s in sources if isinstance(s, dict)]
    lists = [s for s in sources if isinstance(s, list)]
    keys = _locals_keys_reached(states, target, union_tag, depth=len(path)) if dicts else ()
    if keys:
        yield path, keys
    if dicts:
        names: dict[str, None] = dict.fromkeys(chain.from_iterable(dicts))
        naming = next((d for d in reversed(dicts) if names_something(d, union_tag)), None)
        for name in names:
            if name in keys:
                continue  # inside a namespace everything is free-form data
            if isinstance(name, ListOp):
                continue  # an op no layer below gave a list to make: no position to walk at
            below = _step_states(states, name, len(path), naming, union_tag)
            yield from _iter_namespace_nodes([d.get(name) for d in dicts], target, union_tag, [*path, name], below)
    if lists:
        for i in range(max(len(x) for x in lists)):
            items = [x[i] for x in lists if i < len(x)]
            below = _step_states(states, str(i), len(path), None, union_tag)
            yield from _iter_namespace_nodes(items, target, union_tag, [*path, str(i)], below)


#: A position the layers below a layer hold, of which that layer says nothing.
_BELOW: Any = object()


class _LayerReading:
    """How the locals walk reads one layer: each node of pending list ops as the list it makes over the layers below.

    An item an op appends lands at the position ``build()`` gives it, after what lies below,
    so a namespace in it is found at the path a flag spells to reach it, and an index patch
    meets the item the op made. What a lower layer holds there stands as ``_BELOW``: the layer
    says nothing of it. A layer that only overrides leaves every namespace as it holds it, the
    very dict, so the checks coerce it in place and a list op in one is refused, never read.

    Dev Notes:
        docs-dev/architecture/locals.md#a-namespace-in-an-item-a-list-op-holds
    """

    def __init__(self, target: Any, union_tag: str, *, declaring: bool) -> None:
        self.target = target
        self.union_tag = union_tag
        self.declaring = declaring

    def read(self, node: Any, below: Any, path: list[str], states: list[_WalkState] | None = None) -> Any:
        """Return *node*, at *path*, read over *below*, the same path of the layers below it.

        *states* are the ways the walk reaches *node*, the root's when omitted. A child is
        stepped to by the class *node* names, else the one *below* names: a key reaches
        construction only from its own layer or a lower one.
        """
        states = [_walk_start(self.target)] if states is None else states
        if isinstance(node, list):
            items = [self.read(v, None, [*path, str(i)], self._step(states, path, str(i))) for i, v in enumerate(node)]
            return node if all(a is b for a, b in zip(items, node, strict=True)) else items
        if not isinstance(node, dict):
            return node
        if any(isinstance(k, ListOp) for k in node) and (listed := self._listed(node, below, path, states)) is not None:
            return listed
        keys = () if self.declaring else _locals_keys_reached(states, self.target, self.union_tag, depth=len(path))
        naming = next((n for n in (node, below) if names_something(n, self.union_tag)), None)
        out = {
            k: v
            if isinstance(k, ListOp) or k in keys
            else self.read(v, _below_at(below, k), [*path, str(k)], self._step(states, path, str(k), naming))
            for k, v in node.items()
        }
        return node if all(out[k] is v for k, v in node.items()) else out

    def _step(self, states: list[_WalkState], path: list[str], part: str, naming: Any = None) -> list[_WalkState]:
        """Return the ways the walk reaches *part* below *path*: none in a declaring layer, which seeks no namespace."""
        return [] if self.declaring else _step_states(states, part, len(path), naming, self.union_tag)

    def _listed(self, node: MergeDict, below: Any, path: list[str], states: list[_WalkState]) -> list[Any] | None:
        """Return the list the ops *node* holds make over *below*, None where its positions are unknown.

        A base carried as an expression is unknown until resolution, and an op that does not
        apply is the merge's and construction's to refuse, with their own message.
        """
        base = node.get(ListOp.BASE, _BELOW)
        if isinstance(base, list):
            working = [
                self.read(v, None, [*path, str(i)], self._step(states, path, str(i))) for i, v in enumerate(base)
            ]
        elif base is _BELOW:
            working = [_BELOW] * (len(below) if isinstance(below, list) else 0)
        elif isinstance(base, _DeleteSentinel):
            working = []
        else:
            return None
        ops: MergeDict = {k: v for k, v in node.items() if isinstance(k, ListOp) and k is not ListOp.BASE}
        if ListOp.APPEND in ops:
            appended = _to_append_list(ops[ListOp.APPEND])
            ops[ListOp.APPEND] = [
                self.read(v, None, [*path, str(at)], self._step(states, path, str(at)))
                for at, v in enumerate(appended, start=len(working))
            ]
        spelled = ".".join(path)
        try:
            working = _apply_list_ops(working, ops, spelled, _SHAPE)
            self._lay_index_patches(working, node, path, states)
        except (ConfargError, ValueError):
            return None
        return working

    def _lay_index_patches(
        self, working: list[Any], node: MergeDict, path: list[str], states: list[_WalkState]
    ) -> None:
        """Lay each index patch *node* holds over the item of *working* it reaches, in place.

        Raises:
            ConfargError: If an index reaches no item.
            ValueError: If a key spells no index.
        """
        spelled = ".".join(path)
        for k, v in node.items():
            if isinstance(k, ListOp):
                continue
            index = _resolve_index(int(k), len(working), spelled, "patch")
            patch = self.read(v, None, [*path, str(index)], self._step(states, path, str(index)))
            item = working[index]
            working[index] = {**item, **patch} if isinstance(item, dict) and isinstance(patch, dict) else patch


def _below_at(below: Any, key: Any) -> Any:
    """Return what *below* holds at *key*, a list by the index *key* spells, None where it holds nothing."""
    if isinstance(below, dict):
        return below.get(key)
    if isinstance(below, list):
        try:
            return below[int(key)]
        except (ValueError, IndexError):
            return None
    return None


def _apply_locals_layer(  # noqa: PLR0913  # three source layers plus the two names they are read against
    target: Any,
    config_data: MergeDict,
    env_data: MergeDict,
    cli_data: MergeDict,
    *,
    union_tag: str,
    config_flag: str,
    below_cli: MergeDict,
) -> None:
    """Validate and coerce every local-variables namespace across the three layers.

    *config_data* declares the locals; overrides in *env_data* and *cli_data* are
    checked against it and coerced in place. Namespaces are found at every node, an item
    a list op holds at the position ``build()`` gives it, each layer read over the layers
    below it, *below_cli* being what lies under the command line.

    Dev Notes:
        docs-dev/architecture/locals.md
        docs-dev/architecture/locals.md#a-namespace-in-an-item-a-list-op-holds
    """
    declaring = _LayerReading(target, union_tag, declaring=True)
    overriding = _LayerReading(target, union_tag, declaring=False)
    config_read = declaring.read(config_data, None, [])
    env_read = overriding.read(env_data, config_read, [])
    cli_read = overriding.read(cli_data, declaring.read(below_cli, None, []), [])
    for path, keys in _iter_namespace_nodes([config_read, env_read, cli_read], target, union_tag):
        node = _lookup_path(config_read, path)
        node = node if isinstance(node, dict) else {}
        declaring = [key for key in keys if key in node]
        if len(declaring) > 1:
            raise LocalsError.ambiguous(declaring, ".".join(path))
        for key in keys:
            where = ".".join([*path, key])
            if key in node:
                _check_locals_are_typed(node[key], where, where)
            declared = node.get(key, {})
            for source, source_data in (("environment", env_read), ("command line", cli_read)):
                sub = _lookup_path(source_data, path)
                if isinstance(sub, dict) and key in sub:
                    _apply_locals_overrides(declared, sub[key], where, config_flag, source)


def _merge_sources(
    target: Any,
    parse_cli: Callable[[MergeDict], MergeDict],
    cli_configs: Sequence[tuple[str, str]],
    options: _Options,
    *,
    copies: Copies,
) -> MergeDict:
    """Merge the CLI data with env vars and config files in priority order.

    The layers are read lowest first, each typed over what lies below it: the config level,
    then the environment over it, then argv over both, so a node a lower layer names types
    the keys a higher one writes below it.

    Args:
        target: The target type, guiding env-var parsing.
        parse_cli: Parses argv over what the layers below it hold, merged, into the nested
            dict of CLI-provided field values (highest priority).
        cli_configs: (subpath, mount value) pairs from ``--config[.subpath][+]`` flags,
            in left-to-right CLI order.
        options: The caller's resolved options; ``argv`` and ``cli_prefix`` are not
            read, *parse_cli* reading argv and *cli_configs* naming its files.
        copies: The configuration's copy budget, which every document read charges.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key

    Returns:
        A plain dict of the merged configuration, with expression strings intact. A list
        operation that only ``build()`` can apply stays in it, keyed by a
        :class:`confarg.ListOp`.

    Config file loading order (all at the same priority level, below inline
    env vars and CLI args; later files win on conflict):
        1. ``files`` — in the order given.
        2. ``env_config`` — the single global path named by that env var (if set).
        3. ``<config_flag>__*`` env vars — sorted lexicographically, i.e. by
           subpath depth (shallower paths first).
        4. ``cli_configs`` — in left-to-right CLI order.
    """
    config_flag, union_tag = options.config_flag, options.union_tag
    locals_keys = _locals_keys(target, union_tag)
    if config_flag in locals_keys:
        msg = (
            f"config_flag is {config_flag!r}, which is also a name of the local-variables"
            f" namespace. The config-file flag is intercepted before field lookup, so"
            f" --{config_flag}.<name> could never reach a local variable."
            f" Pass a different config_flag to merge()/load(), e.g. config_flag='conf'."
        )
        raise ConfargError(msg)

    # 1. The config level, then the environment over it
    config_data, env_data = _lower_layers(target, cli_configs, options, copies=copies)
    root = merge_root(target, union_tag)
    # 2. argv over both
    below_cli = _deep_merge(config_data, env_data, at=root)
    cli_data = parse_cli(below_cli)

    _apply_locals_layer(
        target,
        config_data,
        env_data,
        cli_data,
        union_tag=union_tag,
        config_flag=config_flag,
        below_cli=below_cli,
    )

    # 3. Merge: config (lowest) → env → CLI (highest)
    merged = _deep_merge(config_data, env_data, at=root)
    merged = _deep_merge(merged, cli_data, at=root)
    # Every layer is in: a whole-field delete has cut the ops after it off from all of them.
    merged = _drop_deleted_bases(merged)

    # Every file is mounted now: rewrite configuration-root references (${::x}) as plain
    # paths. Node-relative ones (${.x}) are deliberately left alone -- resolving them here
    # would pin a list element to its current index.
    # See docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring.
    return canonicalize_references(merged)


def _lower_layers(
    target: Any,
    cli_configs: Sequence[tuple[str, str]],
    options: _Options,
    *,
    copies: Copies,
) -> tuple[MergeDict, MergeDict]:
    """Return the config level and the environment, each typed over what lies below it.

    The config files load in priority order (all config-level, below inline env/CLI), then
    the environment is parsed over them, so a node a file names types the variables below it.
    """
    env, env_config = options.env, options.env_config
    config_flag, union_tag = options.config_flag, options.union_tag
    # Exclude the env_config key so it is not mistakenly treated as a field.
    env_for_fields = {k: v for k, v in env.items() if k != env_config} if env_config else env
    env_prefix = options.env_prefix

    file_entries: list[tuple[str, Any]] = [("", f) for f in options.files]
    if env_config and (env_config_path := env.get(env_config)):
        file_entries.append(("", env_config_path))
    env_configs = (
        []
        if env_prefix is None
        else _env_config_pointers(env_for_fields, env_prefix, options.env_separator, target, config_flag, union_tag)
    )
    env_configs.sort(key=operator.itemgetter(0))
    root = merge_root(target, union_tag)
    config_data = _load_subpath_files(file_entries + env_configs, root, copies=copies)
    for subpath, value in cli_configs:
        fdata = _load_cli_config(value, subpath, config_flag, root, copies=copies)
        config_data = _deep_merge(config_data, fdata, at=root)

    env_data: MergeDict = {}
    if env_prefix is not None:
        env_data, _ = _parse_env(
            env_for_fields,
            env_prefix,
            options.env_separator,
            target,
            config_flag,
            union_tag,
            below=config_data,
        )
    return config_data, env_data


def below_argv(target: Any, cli_configs: Sequence[tuple[str, str]], options: _Options) -> MergeDict:
    """Return what the layers below argv hold, merged, for registration, which types argv's flags by it.

    Best effort, as the rest of registration: a layer that fails to load or to parse
    raises its error at the merge, so here it holds nothing, and what it warns about the
    merge warns about, once. It reads with a copy budget of its own: the merge reads again.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            config_data, env_data = _lower_layers(target, cli_configs, options, copies=Copies())
        return _deep_merge(config_data, env_data, at=merge_root(target, options.union_tag))
    except Exception:  # noqa: BLE001  # a failing layer is the merge's to report
        return {}

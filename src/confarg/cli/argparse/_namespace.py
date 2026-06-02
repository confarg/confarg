# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert an argparse Namespace into a nested dict for dataclass construction."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping, Sequence

from confarg import _defaults
from confarg._files import _load_subpath_files
from confarg._import import _import_dotted
from confarg._merge import _deep_merge, _set_nested
from confarg._parse_env import _parse_env
from confarg._types import (
    _callable_return_type,
    _is_callable,
    _is_dict,
    _is_struct,
    _resolve_type,
    _StrToken,
    _union_args_no_none,
    _unwrap_optional,
)
from confarg.cli.argparse._build import _resolve_struct
from confarg.dictexpr import resolve_expressions
from confarg.exceptions import SymbolImportError
from confarg.typedload import construct


def _str_token(v: Any) -> Any:
    """Wrap str in _StrToken; pass through non-str unchanged."""
    return _StrToken(v) if isinstance(v, str) else v


def _merge_blob_into_spec(blob: dict[str, Any], spec: dict[str, Any], bind: dict[str, Any]) -> dict[str, Any]:
    """Merge a pre-existing blob dict with the newly assembled spec, combining bind entries."""
    merged = {**blob, **{k: v for k, v in spec.items() if k != "bind"}}
    blob_bind = blob.get("bind", {})
    if isinstance(blob_bind, dict) and bind:
        merged["bind"] = {**blob_bind, **bind}
    elif bind:
        merged["bind"] = bind
    return merged


def _collect_fn_identity(
    flat: dict[str, Any],
    fn_key: str,
    cls_key: str,
    call_key: str,
) -> dict[str, Any]:
    """Extract fn/class/call identity entries from flat into a spec dict."""
    spec: dict[str, Any] = {}
    for src_key, dest_name in ((fn_key, "fn"), (cls_key, "class"), (call_key, "call")):
        if src_key in flat:
            spec[dest_name] = _str_token(flat[src_key])
    return spec


def _collect_factory_kwargs(
    flat: dict[str, Any],
    flag_prefix: str,
    bind_prefix: str,
    reserved: set[str],
) -> dict[str, Any]:
    """Collect top-level factory kwargs (positional result fields) from flat namespace."""
    kwargs: dict[str, Any] = {}
    for k, v in flat.items():
        if k.startswith(flag_prefix) and k not in reserved and not k.startswith(bind_prefix):
            tail = k[len(flag_prefix) :]
            if "." not in tail:
                kwargs[tail] = _str_token(v)
    return kwargs


def _collect_callable_spec(
    flat: dict[str, Any],
    flag: str,
    core: Any,
    result: dict[str, Any],
) -> None:
    """Build and store the callable spec dict from flat namespace entries for flag."""
    fn_key = f"{flag}.fn"
    cls_key = f"{flag}.class"
    call_key = f"{flag}.call"
    bind_prefix = f"{flag}.bind."
    flag_prefix = f"{flag}."
    reserved = {fn_key, cls_key, call_key}

    spec = _collect_fn_identity(flat, fn_key, cls_key, call_key)

    bind: dict[str, Any] = {k[len(bind_prefix) :]: _str_token(v) for k, v in flat.items() if k.startswith(bind_prefix)}
    if bind:
        spec["bind"] = bind

    ret = _callable_return_type_for(core)
    if (ret is not None and isinstance(ret, type) and ret is not type(None)) or cls_key in flat or fn_key in flat:
        spec.update(_collect_factory_kwargs(flat, flag_prefix, bind_prefix, reserved))

    if flag in flat:
        blob = flat[flag]
        if isinstance(blob, str) and not spec:
            _set_nested(result, flag.split("."), _StrToken(blob))
            return
        if isinstance(blob, dict):
            spec = _merge_blob_into_spec(blob, spec, bind)

    if spec:
        _set_nested(result, flag.split("."), spec)


def _callable_return_type_for(core: Any) -> Any | None:
    """Return the return type of a Callable type hint, or None."""
    return _callable_return_type(core)


def _collect_ns_union_field(
    flat: dict[str, Any],
    flag: str,
    resolved: Any,
    union_tag: str,
    result: dict[str, Any],
) -> None:
    """Handle a multi-variant union field: pick up the class-tag and recurse into the resolved variant."""
    non_none = _union_args_no_none(resolved)
    if not any(_is_struct(_resolve_type(v)) for v in non_none):
        return
    tag_key = f"{flag}.{union_tag}"
    if tag_key not in flat:
        return
    class_tag = flat[tag_key]
    _set_nested(result, [*flag.split("."), union_tag], _str_token(class_tag))
    try:
        cls = _import_dotted(str(class_tag))
        if isinstance(cls, type) and _is_struct(_resolve_type(cls)):
            _collect_ns_fields(flat, cls, flag, union_tag, result)
    except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
        pass


def _collect_ns_inheritance(
    flat: dict[str, Any],
    tp: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
) -> None:
    """Handle inheritance dispatch: if the union_tag key is in flat at this level, recurse into the named subclass.

    The `cls is not tp` guard prevents infinite recursion when the subclass
    itself re-enters this function and still sees the same tag key.
    """
    tag_key = f"{prefix}.{union_tag}" if prefix else union_tag
    if tag_key not in flat:
        return
    class_tag = flat[tag_key]
    try:
        cls = _import_dotted(str(class_tag))
        if isinstance(cls, type) and _is_struct(_resolve_type(cls)) and cls is not tp:
            tag_path = ([*prefix.split(".")] if prefix else []) + [union_tag]
            _set_nested(result, tag_path, _str_token(class_tag))
            _collect_ns_fields(flat, cls, prefix, union_tag, result)
    except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
        pass


def _collect_ns_fields(
    flat: dict[str, Any],
    target: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
) -> None:
    """Walk target and copy matching flat-namespace entries into nested dict."""
    setup = _resolve_struct(target)
    if setup is None:
        return
    _tp, flds, hints = setup

    for name in flds:
        if name == union_tag:
            continue

        raw_type = hints.get(name, Any)
        resolved = _resolve_type(raw_type)
        flag = f"{prefix}.{name}" if prefix else name

        core = _unwrap_optional(resolved)
        if core is None:
            _collect_ns_union_field(flat, flag, resolved, union_tag, result)
            continue

        if _is_struct(core):
            _collect_ns_fields(flat, core, flag, union_tag, result)
            continue

        if _is_dict(core):
            continue

        if _is_callable(core):
            _collect_callable_spec(flat, flag, core, result)
            continue

        if flag in flat:
            v = flat[flag]
            v = [_str_token(item) for item in v] if isinstance(v, list) else _str_token(v)
            _set_nested(result, flag.split("."), v)

    _collect_ns_inheritance(flat, _tp, prefix, union_tag, result)


def from_namespace(  # noqa: PLR0913
    target: type,
    ns: argparse.Namespace,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    files: Sequence[str | Path] = (),
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = "__",
) -> Any:
    """Construct a dataclass instance from an argparse :class:`~argparse.Namespace`.

    Merges three sources in ascending priority order: config files, environment
    variables, then CLI arguments from the Namespace.  This mirrors the
    behaviour of :func:`confarg.load`.

    Only fields registered by :func:`populate_parser` are consumed from ``ns``.
    Fields absent from the Namespace fall back to env vars, config files, or
    dataclass defaults; missing required fields raise
    :class:`~confarg.exceptions.MissingFieldError`.

    Args:
        target: The dataclass type to construct.
        ns: The Namespace returned by ``ArgumentParser.parse_args()``.
        union_tag: Discriminator field name (same as :func:`confarg.load`).
        config_flag: Name of the config-file attribute on ``ns`` (default
            ``"config"``).  Must match the ``config_flag`` passed to
            :func:`populate_parser`.  Subkey flags ``--config.<subpath>``
            (registered automatically by :func:`populate_parser`) are also
            consumed.  Set to ``""`` to ignore all config-file attributes.
        files: Additional root-level config file paths to load (lowest priority).
        env: Environment variable mapping.  Defaults to ``os.environ``.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely. Set to ``""``
            to read all env vars without filtering, or to e.g. ``"MYAPP_"`` to
            read only vars with that prefix.
        env_separator: Separator used to split env var names into nested keys.

    Returns:
        An instance of ``target`` populated from all sources.
    """
    if env is None:
        env = os.environ

    # 1. Collect CLI field values from the namespace
    cli_data: dict[str, Any] = {}
    _collect_ns_fields(vars(ns), target, prefix="", union_tag=union_tag, result=cli_data)

    # 2. Collect (subpath, path) pairs for all config files
    file_pairs: list[tuple[str, Path]] = [("", Path(f)) for f in files]
    if config_flag:
        file_pairs.extend(("", Path(f)) for f in getattr(ns, config_flag, None) or [])
        cfg_prefix = f"{config_flag}."
        for key, val in vars(ns).items():
            if key.startswith(cfg_prefix):
                subpath = key[len(cfg_prefix) :]
                file_pairs.extend((subpath, Path(f)) for f in val or [])

    # 3. Load config files
    config_data = _load_subpath_files(file_pairs, union_tag)

    # 4. Parse env vars
    if env_prefix is None:
        env_data: dict[str, Any] = {}
        env_configs: list[tuple[str, Path]] = []
    else:
        env_data, env_configs = _parse_env(env, env_prefix, env_separator, target)
    config_data = _deep_merge(config_data, _load_subpath_files(env_configs, union_tag), union_tag=union_tag)

    # 5. Merge: config < env < CLI
    merged = _deep_merge(config_data, env_data, union_tag=union_tag)
    merged = _deep_merge(merged, cli_data, union_tag=union_tag)

    # 6. Resolve expressions
    merged = resolve_expressions(merged)

    # 7. Construct
    return construct(_resolve_type(target), merged, union_tag=union_tag)

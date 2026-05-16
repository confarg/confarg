# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Environment variable parsing for confarg."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from confarg._errors import ConfargError, ConfargWarning
from confarg._merge import DICT_DELETE, _accumulate_list_delete, _set_nested
from confarg._types import (
    _dict_kv,
    _elem_type,
    _is_callable,
    _is_dict,
    _is_frozenset,
    _is_list,
    _is_set,
    _is_struct,
    _is_struct_like,
    _is_tuple,
    _is_union,
    _is_varlen_collection,
    _resolve_type,
    _StrToken,
    _struct_fields,
    _try_coerce,
    _tuple_types,
    _union_args_no_none,
)


def _resolve_env_parts(target: Any, parts: list[str]) -> tuple[list[str], Any]:
    """Map env var parts to actual field names using case-insensitive matching.

    Walks the type tree to find the correct casing for each path segment.
    Falls back to lowercase when the type is not a dataclass (e.g. dict keys,
    list indices).

    Args:
        target: The root target type.
        parts: A list of env var path segments.

    Returns:
        A tuple of (resolved_parts, leaf_type) where resolved_parts has correct
        casing and leaf_type is the resolved type of the final field (or None).

    Raises:
        ConfargError: If a part matches multiple field names at the same level.
    """
    resolved: list[str] = []
    tp: Any = _resolve_type(target)

    for part in parts:
        name, tp = _match_env_part(tp, part)
        resolved.append(name)

    return resolved, tp


def _match_env_part(tp: Any, part: str) -> tuple[str, Any]:
    """Match a single env var part against the current type level.

    Args:
        tp: The current type being walked.
        part: The env var path segment to match.

    Returns:
        A tuple of (resolved_name, next_type) where next_type may be None.
    """
    if tp is None:
        return part.lower(), None

    tp = _resolve_type(tp)

    if _is_struct(tp):
        flds = _struct_fields(tp)
        matches = [name for name in flds if name.lower() == part.lower()]
        if len(matches) > 1:
            raise ConfargError(
                f"Ambiguous env var segment {part!r}: matches multiple fields {matches} in {tp.__name__}."
                " Check your dataclass definition for duplicate case-insensitive field names."
            )
        if len(matches) == 1:
            return matches[0], flds[matches[0]]
        return part.lower(), None

    if _is_union(tp):
        name_to_types: dict[str, list[Any]] = {}
        for variant in _union_args_no_none(tp):
            v = _resolve_type(variant)
            if _is_struct(v):
                flds = _struct_fields(v)
                for fname in flds:
                    if fname.lower() == part.lower():
                        name_to_types.setdefault(fname, []).append(flds[fname])
        if len(name_to_types) > 1:
            raise ConfargError(
                f"Ambiguous env var segment {part!r}: matches fields"
                f" {sorted(name_to_types.keys())} across union variants."
                " Use a more specific environment variable name or add a discriminator field."
            )
        if len(name_to_types) == 1:
            name = next(iter(name_to_types))
            types = name_to_types[name]
            # Only return a concrete type when all variants agree; otherwise None (defer to construct)
            ft = types[0] if all(t == types[0] for t in types[1:]) else None
            return name, ft
        return part.lower(), None

    if _is_list(tp) or _is_set(tp) or _is_frozenset(tp):
        return part.lower(), _elem_type(tp)

    if _is_tuple(tp):
        tt = _tuple_types(tp)
        if tt is None:
            return part.lower(), _elem_type(tp)
        try:
            idx = int(part)
            if 0 <= idx < len(tt):
                return part.lower(), tt[idx]
        except ValueError:
            pass
        return part.lower(), None

    if _is_dict(tp):
        _, vt = _dict_kv(tp)
        return part.lower(), vt

    return part.lower(), None


def _parse_env(
    env: Mapping[str, str],
    prefix: str,
    separator: str,
    target: Any,
    config_flag: str = "config",
) -> tuple[dict[str, Any], list[tuple[str, Path]]]:
    """Parse environment variables into a nested dict matching the target type.

    Variables are matched by prefix and split by separator into nested keys.
    Field names are matched case-insensitively against the target type tree.
    For non-dataclass targets, the value is stored under a ``__root__`` key.

    A variable whose first segment (after stripping the prefix) matches
    ``config_flag`` (case-insensitive) is treated as a sub-config file pointer:
    the value is a file path, and the remaining segments form the subpath at
    which the file's contents will be merged (e.g. ``CONFARG_CONFIG__DB=db.yaml``
    merges ``db.yaml`` under the ``db`` key).

    Args:
        env: The environment variable mapping to scan.
        prefix: Required prefix for relevant variables (empty string to match all).
        separator: Separator used to split variable names into nested keys.
        target: The target type, used to determine dataclass vs scalar handling.
        config_flag: The magic segment name that marks a sub-config file pointer.

    Returns:
        A tuple of (data_dict, env_configs) where data_dict contains inline values
        and env_configs is a list of (subpath, Path) pairs for deferred file loading.

    Raises:
        ConfargError: If an env var segment matches multiple field names.
    """
    data: dict[str, Any] = {}
    env_configs: list[tuple[str, Path]] = []
    is_struct = _is_struct_like(_resolve_type(target))

    for orig_key, value in env.items():
        key = orig_key
        if prefix:
            if not key.startswith(prefix):
                continue
            key = key[len(prefix) :]
            key = key.removeprefix(separator)

        parts = key.split(separator) if separator in key else [key]

        # Config flag: CONFARG_CONFIG[__subpath]=file.yaml → defer to file loading
        if parts[0].lower() == config_flag.lower():
            subpath_parts = parts[1:]
            if subpath_parts:
                resolved_parts, _ = _resolve_env_parts(target, subpath_parts)
                subpath = ".".join(resolved_parts)
            else:
                subpath = ""
            env_configs.append((subpath, Path(value)))
            continue

        # Delete sentinel: FOO__BAR- deletes key BAR from FOO (dict-key deletion).
        # FOO__ITEMS__1- deletes index 1 from FOO__ITEMS (list-index deletion).
        if parts[-1].endswith("-") and len(parts[-1]) > 1:
            raw_last = parts[-1][:-1]
            try:
                delete_idx = int(raw_last)
                is_list_delete = True
            except ValueError:
                is_list_delete = False
                delete_idx = -1

            if is_list_delete:
                parent_raw = parts[:-1]
                if parent_raw:
                    parent_parts, _ = _resolve_env_parts(target, parent_raw)
                else:
                    parent_parts = []
                _accumulate_list_delete(data, parent_parts, delete_idx, orig_key)
            else:
                del_parts_raw = parts[:-1] + [raw_last]
                del_parts, _ = _resolve_env_parts(target, del_parts_raw)
                _set_nested(data, del_parts, DICT_DELETE)
            continue

        if not is_struct:
            # For scalar targets, store under sentinel key
            data["__root__"] = _try_coerce(_resolve_type(target), _StrToken(value))
            continue

        parts, ft = _resolve_env_parts(target, parts)
        # Skip env vars whose first segment doesn't match a known field
        root_tp = _resolve_type(target)
        if _is_struct(root_tp) and parts[0] not in _struct_fields(root_tp):
            known = sorted(_struct_fields(root_tp).keys())
            warnings.warn(
                f"Environment variable {orig_key!r} has no matching field"
                f" (segment {parts[0]!r} not found in {root_tp.__name__})."
                f" Known fields: {known}. The variable will be ignored.",
                ConfargWarning,
                stacklevel=3,
            )
            continue
        if _is_union(root_tp):
            struct_variants = [_resolve_type(v) for v in _union_args_no_none(root_tp) if _is_struct(_resolve_type(v))]
            if struct_variants and not any(parts[0] in _struct_fields(v) for v in struct_variants):
                all_fields = sorted({f for v in struct_variants for f in _struct_fields(v)})
                warnings.warn(
                    f"Environment variable {orig_key!r} has no matching field"
                    f" (segment {parts[0]!r} not found in any union variant)."
                    f" Known fields across variants: {all_fields}. The variable will be ignored.",
                    ConfargWarning,
                    stacklevel=3,
                )
                continue
        if value.startswith(("[", "{")):
            accepts_obj = value.startswith("{") and (
                _is_struct(ft)
                or _is_dict(ft)
                or _is_callable(ft)
                or (_is_union(ft) and any(_is_struct(_resolve_type(v)) for v in _union_args_no_none(ft)))
            )
            accepts_arr = value.startswith("[") and (
                _is_varlen_collection(ft)
                or _is_tuple(ft)
                or (
                    _is_union(ft)
                    and any(
                        _is_varlen_collection(_resolve_type(v)) or _is_tuple(_resolve_type(v))
                        for v in _union_args_no_none(ft)
                    )
                )
            )
            if accepts_obj or accepts_arr:
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list | dict):
                        _set_nested(data, parts, parsed)
                        continue
                except json.JSONDecodeError:
                    pass
        _set_nested(data, parts, _try_coerce(ft, _StrToken(value)))

    return data, env_configs

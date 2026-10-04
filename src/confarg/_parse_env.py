# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Environment variable parsing into a nested dict shaped by the target type.

Dev Notes:
    docs-dev/architecture/environment-parsing.md#environment-parsing
"""

from __future__ import annotations

import json
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

from confarg import _defaults
from confarg._cast import JSON_CAST_NAME, fold_root_json, resolve_forced_value
from confarg._merge import DICT_DELETE, _accumulate_list_delete, _set_nested
from confarg._parse_cli import (
    _accepts_object_value,
    _check_mount_subpath,
    _field_types,
    _locals_segment_index,
    _member_names,
    _open_callable_shorthand,
    _resolve_field_type,
    _segment_names_real_field,
    detect_force_cast,
)
from confarg._types import (
    _is_seq_variant,
    _is_struct,
    _is_struct_like,
    _is_union,
    _resolve_type,
    _StrToken,
    _struct_fields,
    _union_args_no_none,
    _union_has_seq_variant,
)
from confarg.exceptions import ConfargError, ConfargWarning
from confarg.typedload._coerce import _try_coerce


def _resolve_env_parts(target: Any, parts: list[str], union_tag: str) -> tuple[list[str], Any]:
    """Spell each env var segment as the member it names, then type the path by the canonical walk.

    The environment adds one rule to the CLI channel's path, case-insensitivity, and only
    that rule lives here: :func:`_env_spelling` turns each segment into the exact spelling
    the walk compares, and :func:`~confarg._parse_cli._resolve_field_type` types the
    spelled path exactly as it types a flag's. So an env variable merges what the flag of
    the same path merges (REF-73).

    Args:
        target: The root target type.
        parts: A list of env var path segments.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        A tuple of (resolved_parts, leaf_type) where resolved_parts has correct
        casing and leaf_type is the resolved type of the final field (or None).

    Raises:
        ConfargError: If a part matches several member spellings at its position.

    Dev Notes:
        docs-dev/architecture/environment-parsing.md#environment-parsing
    """
    resolved: list[str] = []
    for part in parts:
        resolved.append(_env_spelling(target, resolved, part, union_tag))
    return resolved, _resolve_field_type(target, resolved, union_tag)


def _env_spelling(target: Any, prefix: list[str], part: str, union_tag: str) -> str:
    """Return the exact spelling env segment *part* takes below the spelled path *prefix*.

    A member it names case-insensitively, among the named members of every type the walk
    reaches at *prefix* -- each union variant, each subclass-only field; else the union
    tag by its own spelling, which the walk downstream compares exactly (BUG-101); else
    the segment lowercased, a dict key or an index the walk reads as it is. A member
    always wins over the tag, as the walk's tag is its fallback.

    Raises:
        ConfargError: If the segment matches several member spellings, which no
            environment variable can tell apart.
    """
    names = {n for tp in _field_types(target, prefix, union_tag) for n in _member_names(tp)}
    matches = sorted(n for n in names if n.lower() == part.lower())
    if len(matches) > 1:
        where = ".".join(prefix) or "the root"
        msg = (
            f"Ambiguous env var segment {part!r}: matches fields {matches} at {where}."
            " An environment variable cannot tell spellings that differ only by case apart."
        )
        raise ConfargError(msg)
    if matches:
        return matches[0]
    if part.lower() == union_tag.lower():
        return union_tag
    return part.lower()


def _handle_env_config_flag(  # noqa: PLR0913  # the check needs the tag, the message the spelling the user typed
    parts: list[str],
    target: Any,
    env_configs: list[tuple[str, str]],
    value: str,
    union_tag: str,
    orig_key: str,
) -> None:
    """Append a (subpath, mount value) pair to env_configs for a CONFIG[__subpath] env var.

    The value is kept as written: the pipeline reads it as an ``__include__`` value, so a
    ``{"path": …, "orient": …}`` object is spelled here exactly as it is in a file
    (docs-dev/architecture/config-files/mounting.md#mounting). The subpath is checked against
    *target* after it is resolved — a segment that matches no field is an error here,
    not a silent mount that surfaces much later as an unknown-field error from ``build()``.
    """
    subpath_parts = parts[1:]
    if subpath_parts:
        resolved_parts, _ = _resolve_env_parts(target, subpath_parts, union_tag)
        subpath = ".".join(resolved_parts)
        # Resolved parts, because the env match is case-insensitive and the walk the
        # check runs is exact.
        _check_mount_subpath(target, subpath, union_tag, orig_key)
    else:
        subpath = ""
    env_configs.append((subpath, value))


def _handle_env_delete(orig_key: str, parts: list[str], target: Any, data: dict[str, Any], union_tag: str) -> None:
    """Apply a delete sentinel (FOO__BAR- or FOO__ITEMS__1-) to data."""
    raw_last = parts[-1][:-1]
    try:
        delete_idx = int(raw_last)
        is_list_delete = True
    except ValueError:
        is_list_delete = False
        delete_idx = -1

    if is_list_delete:
        parent_raw = parts[:-1]
        parent_parts, _ = _resolve_env_parts(target, parent_raw, union_tag) if parent_raw else ([], None)
        _accumulate_list_delete(data, parent_parts, delete_idx, orig_key)
    else:
        del_parts, _ = _resolve_env_parts(target, [*parts[:-1], raw_last], union_tag)
        _set_nested(data, del_parts, DICT_DELETE)


def _apply_env_json_cast(  # noqa: PLR0913  # root and nested placement need distinct sinks
    orig_key: str,
    parts: list[str],
    target: Any,
    value: str,
    data: dict[str, Any],
    root_json: list[dict[str, Any]],
    union_tag: str,
) -> bool:
    """Apply a ``json`` force-cast (``FOO__DB__json``, or ``FOO_JSON`` at the root).

    Mirrors the CLI ``.json`` suffix, including the bare root form: whether the trailing
    segment is a cast at all is decided by the canonical
    :func:`~confarg._parse_cli.detect_force_cast` (a real field/key named ``json`` wins).
    A nested cast is stored at the parent path; a root cast injects the whole
    configuration — collected into ``root_json`` and folded in as a base by
    :func:`~confarg._cast.fold_root_json`, so per-field env vars win over it.  Returns
    True when handled.  Hard-errors on invalid JSON, matching the CLI's explicit-intent
    semantics.
    """
    if parts[-1].lower() != JSON_CAST_NAME:
        return False
    parent_parts, _ = _resolve_env_parts(target, parts[:-1], union_tag) if parts[:-1] else ([], None)
    path, cast_name = detect_force_cast([*parent_parts, JSON_CAST_NAME], target, union_tag)
    if cast_name is None:
        return False
    decoded = resolve_forced_value(cast_name, value, flag=orig_key)
    if path:
        _set_nested(data, path, decoded)
        return True
    if not _is_struct_like(_resolve_type(target)):
        # Non-struct root: the decoded value *is* the configuration, whatever its shape.
        # The environment has no order for "last typed wins" to read, so the plain
        # variable refines the cast, as a per-field one does on a struct root.
        data.setdefault(_defaults.ROOT_KEY, decoded)
        return True
    if not isinstance(decoded, dict):
        raise ConfargError.root_cast_not_object(orig_key, decoded)
    root_json.append(decoded)
    return True


def _warn_unknown_env_field(orig_key: str, parts: list[str], root_tp: Any, union_tag: str) -> bool:
    """Warn and return True if the env var's first segment names no real member of the root.

    Real membership is the canonical :func:`~confarg._parse_cli._segment_names_real_field`'s
    to answer — the same predicate the CLI's casts and locals consult — so the union
    tag and a subclass-only field name a member here exactly as the CLI channel
    accepts them (BUG-90).

    Dev Notes:
        docs-dev/architecture/environment-parsing.md#environment-parsing
    """
    if _segment_names_real_field(root_tp, parts[0], union_tag):
        return False
    if _is_union(root_tp):
        struct_variants = [_resolve_type(v) for v in _union_args_no_none(root_tp) if _is_struct(_resolve_type(v))]
        all_fields = sorted({f for v in struct_variants for f in _struct_fields(v)})
        warnings.warn(
            f"Environment variable {orig_key!r} has no matching field"
            f" (segment {parts[0]!r} not found in any union variant)."
            f" Known fields across variants: {all_fields}. The variable will be ignored.",
            ConfargWarning,
            stacklevel=4,
        )
        return True
    known = sorted(_struct_fields(root_tp).keys())
    warnings.warn(
        f"Environment variable {orig_key!r} has no matching field"
        f" (segment {parts[0]!r} not found in {root_tp.__name__})."
        f" Known fields: {known}. The variable will be ignored.",
        ConfargWarning,
        stacklevel=4,
    )
    return True


def _accepts_json_for(ft: Any, value: str) -> bool:
    """Return True when a ``[``/``{``-led env value should be JSON-parsed for type ``ft``.

    The opening bracket must match a shape the type can accept, and the shape is not this
    channel's question to answer: ``{`` defers to
    :func:`~confarg._parse_cli._accepts_object_value`, the predicate the CLI whole-value
    flag already consults, and ``[`` to :func:`~confarg._types._is_seq_variant` and its
    union arm.  Asking here again is what let a plain class take the blob from the
    environment while the CLI refused it (BUG-39).

    Dev Notes:
        docs-dev/architecture/environment-parsing.md#environment-parsing
    """
    if value.startswith("{"):
        return _accepts_object_value(ft)
    if value.startswith("["):
        return _is_seq_variant(ft) or _union_has_seq_variant(ft)
    return False


def _store_env_value(parts: list[str], ft: Any, value: str, data: dict[str, Any]) -> None:
    """Parse an env var string value and store it at the resolved path in data."""
    if _accepts_json_for(ft, value):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list | dict):
                _set_nested(data, parts, parsed)
                return
        except json.JSONDecodeError:
            pass
    _set_nested(data, parts, _try_coerce(ft, _StrToken(value)))


def _parse_env(  # noqa: PLR0913  # one parameter per reserved name the env channel must intercept
    env: Mapping[str, str],
    prefix: str,
    separator: str,
    target: Any,
    config_flag: str = _defaults.CONFIG_FLAG,
    union_tag: str = _defaults.UNION_TAG,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
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
        union_tag: The field name used as a discriminator tag in union types; also
            used to find the local-variables namespace at each node of the path.
            Variables addressing that namespace are stored raw, without the
            unknown-field warning, and checked later by the pipeline.

    Returns:
        A tuple of (data_dict, env_configs) where data_dict contains inline values
        and env_configs is a list of (subpath, mount value) pairs for deferred file loading.

    Raises:
        ConfargError: If an env var segment matches multiple field names.
    """
    data: dict[str, Any] = {}
    env_configs: list[tuple[str, str]] = []
    root_json: list[dict[str, Any]] = []  # objects from a root-level `json` cast, folded in below fields
    is_struct = _is_struct_like(_resolve_type(target))

    for orig_key, value in env.items():
        key = orig_key
        if prefix:
            if not key.startswith(prefix):
                continue
            key = key[len(prefix) :].removeprefix(separator)

        parts = key.split(separator) if separator in key else [key]

        if config_flag and parts[0].lower() == config_flag.lower():
            _handle_env_config_flag(parts, target, env_configs, value, union_tag, orig_key)
            continue

        if parts[-1].endswith("-") and len(parts[-1]) > 1:
            _handle_env_delete(orig_key, parts, target, data, union_tag)
            continue

        if _apply_env_json_cast(orig_key, parts, target, value, data, root_json, union_tag):
            continue

        if not is_struct:
            data[_defaults.ROOT_KEY] = _try_coerce(_resolve_type(target), _StrToken(value))
            continue

        parts, ft = _resolve_env_parts(target, parts, union_tag)
        # Locals are not target fields: skip the unknown-field warning and store the raw
        # token; _pipeline checks and coerces them (docs-dev/architecture/locals.md).
        is_locals = _locals_segment_index(target, parts, union_tag) is not None
        if not is_locals and _warn_unknown_env_field(orig_key, parts, _resolve_type(target), union_tag):
            continue
        if is_locals:
            ft = None

        # Same rule as the CLI: a bare callable shorthand already stored at a prefix of
        # this path is a spec this variable refines, not a scalar it replaces.
        _open_callable_shorthand(data, parts, target, union_tag)
        _store_env_value(parts, ft, value, data)

    return fold_root_json(data, root_json, union_tag), env_configs

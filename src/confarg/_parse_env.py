# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Environment variable parsing into a nested dict shaped by the target type.

Dev Notes:
    docs-dev/architecture/environment-parsing.md#environment-parsing
"""

from __future__ import annotations

import contextlib
import json
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

from confarg import _defaults
from confarg._cast import JSON_CAST_NAME, decode_json, fold_root_json, resolve_forced_value
from confarg._merge import (
    APPEND_SUFFIX,
    DELETE_SUFFIX,
    DICT_DELETE,
    MergeDict,
    _accumulate_list_delete,
    _set_nested,
)
from confarg._parse_cli import (
    _accepts_object_value,
    _appended_element_type,
    _check_mount_subpath,
    _collect_append_items,
    _delete_index,
    _EqValue,
    _field_types,
    _locals_keys,
    _locals_segment_index,
    _member_names,
    _open_callable_shorthand,
    _path_unknown,
    _reserved_segment,
    _resolve_field_type,
    _restart_restated_node,
    _sequence_refusal,
    _walk_target,
    _write_append,
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


def _handle_env_config_flag(  # noqa: PLR0913, PLR0917  # the check needs the tag, the message its typed spelling
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
        # The append suffix is no part of the field's name: the segment is spelled without it.
        suffix = APPEND_SUFFIX if _is_env_append(subpath_parts) else ""
        spelled = [*subpath_parts[:-1], subpath_parts[-1].removesuffix(suffix)]
        resolved_parts, _ = _resolve_env_parts(target, spelled, union_tag)
        subpath = ".".join(resolved_parts) + suffix
        # Resolved parts, because the env match is case-insensitive and the walk the
        # check runs is exact.
        _check_mount_subpath(target, subpath, union_tag, orig_key)
    else:
        subpath = ""
    env_configs.append((subpath, value))


def _refuse_root_config_append(orig_key: str, parts: list[str], separator: str) -> None:
    """Refuse a bare ``CONFIG+``, which names no field to append to.

    Raises:
        ConfargError: If *parts* is the config segment alone, with the append suffix.
    """
    if len(parts) == 1 and _is_env_append(parts):
        msg = (
            f"Environment variable {orig_key!r} requires a field path to append to."
            f" Use {orig_key[:-1]}{separator}<FIELD>{APPEND_SUFFIX}=/path/to/file."
        )
        raise ConfargError(msg)


def _refuse_below_a_sequence(orig_key: str, parts: list[str], target: Any, union_tag: str) -> None:
    """Refuse a variable whose spelled path *parts* puts a segment naming no element below a sequence.

    Raises:
        ConfargError: If a sequence refuses a segment of the path (BUG-170).

    Dev Notes:
        docs-dev/architecture/cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index
    """
    at = _sequence_refusal(target, parts, union_tag)
    if at is not None:
        msg = (
            f"Environment variable {orig_key!r} has no matching field"
            f" (segment {parts[at]!r} names no element of '{'.'.join(parts[:at])}')."
        )
        raise ConfargError(msg)


def _refuse_reserved_key(orig_key: str, parts: list[str]) -> None:
    """Refuse a variable whose path spells a key confarg reserves, as its flag is refused.

    A segment is compared lowercased, as the walk reads one naming no member, and a delete's
    suffix is dropped first. Only a separator other than the default ``__`` lets a variable
    spell such a key at all.

    Raises:
        ConfargError: If a segment spells a key of ``_defaults.RESERVED_KEYS``.

    Dev Notes:
        docs-dev/architecture/config-files/reserved-keys.md#reserved-file-only-keys
    """
    segments = [p.lower() for p in parts]
    if _is_env_delete(parts) or _is_env_append(parts):
        segments[-1] = segments[-1][:-1]
    if (reserved := _reserved_segment(segments)) is not None:
        raise ConfargError.reserved_key(orig_key, reserved)


def _handle_env_delete(orig_key: str, del_parts: list[str], data: MergeDict, walk_target: Any, union_tag: str) -> None:
    """Apply a delete (FOO__BAR- or FOO__ITEMS__1-) at *del_parts* in data, as an index or a key delete.

    *del_parts* is the resolved path the delete names, its ``-`` suffix dropped, already
    checked by :func:`_parse_env` as a value variable's path is. Which of the two deletes it
    is, a flag's delete asks too (:func:`~confarg._parse_cli._delete_index`).
    """
    delete_idx = _delete_index(walk_target, del_parts, union_tag)
    if delete_idx is not None:
        _accumulate_list_delete(data, del_parts[:-1], delete_idx, orig_key)
    else:
        _set_nested(data, del_parts, DICT_DELETE)


def _is_env_delete(parts: list[str]) -> bool:
    """Whether the variable spelled *parts* is a delete (``FOO__BAR-``, ``FOO__ITEMS__1-``)."""
    return parts[-1].endswith(DELETE_SUFFIX) and len(parts[-1]) > 1


def _is_env_append(parts: list[str]) -> bool:
    """Whether the variable spelled *parts* is an append (``FOO__ITEMS+``), as ``--items+`` is."""
    return parts[-1].endswith(APPEND_SUFFIX) and len(parts[-1]) > 1


def _addresses_config(parts: list[str], config_flag: str) -> bool:
    """Whether the variable spelled *parts* is a config pointer, ``CONFIG[__SUBPATH][+]``.

    A bare ``CONFIG+`` is one too, a mistake about this variable that
    :func:`_refuse_root_config_append` names, as ``--config+`` is about its flag.
    """
    first = parts[0].lower()
    if len(parts) == 1:
        first = first.removesuffix(APPEND_SUFFIX)
    return bool(config_flag) and first == config_flag.lower()


def _env_cast(parts: list[str], walk_target: Any, union_tag: str) -> tuple[list[str], str] | None:
    """Return the path a ``json`` force-cast variable writes and the cast's name, or None if it is no cast.

    Whether the trailing ``json`` segment is a cast at all is decided by the canonical
    :func:`~confarg._parse_cli.detect_force_cast` (a real field/key named ``json`` wins),
    asked of the *walk_target* a flag's path resolves against. So a dict root's
    ``FOO_JSON`` is its cast: no key of a root set whole is a member.
    """
    if parts[-1].lower() != JSON_CAST_NAME:
        return None
    parent_parts, _ = _resolve_env_parts(walk_target, parts[:-1], union_tag) if parts[:-1] else ([], None)
    path, cast_name = detect_force_cast([*parent_parts, JSON_CAST_NAME], walk_target, union_tag)
    return None if cast_name is None else (path, cast_name)


def _env_order(parts: list[str], key: str, walk_target: Any, union_tag: str) -> tuple[int, int]:
    """Return where the variable spelled *parts* falls in the order the environment is applied in.

    First the depth of the path it writes, so a variable is applied after every variable
    whose path holds its own and refines what they wrote; then, at one path, a delete, a
    ``json`` cast, a plain value and an append, in that order. The variables then merge as the flags
    of the same paths merge when typed in that order, whatever order the mapping yields
    them in.

    Dev Notes:
        docs-dev/architecture/environment-parsing.md#the-broader-variable-applies-first
    """
    if _is_env_delete(parts):
        return len(parts), 0
    if _is_env_append(parts):
        return len(parts), 3
    if (cast := _env_cast(parts, walk_target, union_tag)) is not None:
        return len(cast[0]), 1
    return (len(parts) if key else 0), 2


def _apply_env_json_cast(  # noqa: PLR0913, PLR0917  # root and nested placement need distinct sinks
    orig_key: str,
    parts: list[str],
    walk_target: Any,
    value: str,
    data: MergeDict,
    root_json: list[MergeDict],
    union_tag: str,
    *,
    is_struct: bool,
) -> bool:
    """Apply a ``json`` force-cast (``FOO__DB__json``, or ``FOO_JSON`` at the root).

    Mirrors the CLI ``.json`` suffix, including the bare root form; whether it is a cast
    at all is :func:`_env_cast`'s to answer. A nested cast is stored at the parent path;
    on a non-struct root it sets the value whole; on a struct root it injects the whole
    configuration — collected into ``root_json`` and folded in as a base by
    :func:`~confarg._cast.fold_root_json`, so per-field env vars win over it.  Returns
    True when handled.  Hard-errors on invalid JSON, matching the CLI's explicit-intent
    semantics.
    """
    if (cast := _env_cast(parts, walk_target, union_tag)) is None:
        return False
    path, cast_name = cast
    decoded = resolve_forced_value(cast_name, value, flag=orig_key)
    if path:
        _set_nested(data, path, decoded)
        return True
    if not is_struct:
        # Non-struct root: the decoded value *is* the configuration, whatever its shape.
        # The plain bare variable is applied after it (_env_order) and replaces it.
        data[_defaults.ROOT_KEY] = decoded
        return True
    if not isinstance(decoded, dict):
        raise ConfargError.root_cast_not_object(orig_key, decoded)
    root_json.append(decoded)
    return True


def _warn_unknown_env_field(orig_key: str, parts: list[str], target: Any, walk_target: Any, union_tag: str) -> bool:
    """Warn and return True if the env var's first segment names nothing a flag of the root reaches.

    Whether it does is the canonical :func:`~confarg._parse_cli._path_unknown`'s to answer,
    asked of the *walk_target* every flag resolves against, so a segment is warned about
    here exactly when the CLI refuses it as unknown: the union tag and a subclass-only
    field name a member (BUG-90), and nothing below a non-struct root does, since that
    root is set whole (BUG-115). A delete is asked it of the path it deletes, as the
    value variable of that path is (BUG-182).

    Dev Notes:
        docs-dev/architecture/environment-parsing.md#environment-parsing
    """
    if not _path_unknown(walk_target, parts[:1], union_tag):
        return False
    root_tp = _resolve_type(target)
    if not _is_struct_like(root_tp):
        warnings.warn(
            f"Environment variable {orig_key!r} has no matching field"
            f" (segment {parts[0]!r} is below the {getattr(root_tp, '__name__', root_tp)} root,"
            " which is set whole by the bare prefix variable or its JSON cast)."
            " The variable will be ignored.",
            ConfargWarning,
            stacklevel=4,
        )
        return True
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


def _store_env_value(parts: list[str], ft: Any, value: str, data: MergeDict, orig_key: str) -> None:
    """Parse an env var string value and store it at the resolved path in data.

    A JSON value is data (:func:`~confarg._cast.decode_json`), refused naming *orig_key* if it
    holds a key confarg reserves.
    """
    if _accepts_json_for(ft, value):
        with contextlib.suppress(json.JSONDecodeError):
            parsed = decode_json(value, orig_key)
            if isinstance(parsed, list | dict):
                _set_nested(data, parts, parsed)
                return
    _set_nested(data, parts, _try_coerce(ft, _StrToken(value)))


def _prefixed_variables(
    env: Mapping[str, str],
    prefix: str,
    separator: str,
) -> Iterator[tuple[str, str, list[str], str]]:
    """Yield ``(name, key, segments, value)`` for each variable of *env* carrying *prefix*.

    *key* is the name with the prefix and the separator after it removed, *segments* the
    key split on *separator*.
    """
    for orig_key, value in env.items():
        if prefix and not orig_key.startswith(prefix):
            continue
        key = orig_key.removeprefix(prefix).removeprefix(separator) if prefix else orig_key
        yield orig_key, key, key.split(separator) if separator in key else [key], value


def _parse_env(  # noqa: PLR0913, PLR0917  # one parameter per reserved name the env channel must intercept
    env: Mapping[str, str],
    prefix: str,
    separator: str,
    target: Any,
    config_flag: str = _defaults.CONFIG_FLAG,
    union_tag: str = _defaults.UNION_TAG,
) -> tuple[MergeDict, list[tuple[str, str]]]:
    """Parse environment variables into a nested dict matching the target type.

    Variables are matched by prefix and split by separator into nested keys.
    Field names are matched case-insensitively against the target type tree.
    A non-struct target is set whole, under a ``__root__`` key, by the bare prefix
    variable or its ``JSON`` cast; any other variable names a path below it, which no
    flag reaches either, and is warned about and ignored.

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
    data: MergeDict = {}
    env_configs: list[tuple[str, str]] = []
    root_json: list[MergeDict] = []  # objects from a root-level `json` cast, folded in below fields
    is_struct = _is_struct_like(_resolve_type(target))
    # Paths resolve against the locals-grafted target, as a flag's do; root classification keeps `target`.
    walk_target = _walk_target(target, _locals_keys(target, union_tag))

    variables: list[tuple[tuple[int, int], str, str, list[str], str]] = []
    for orig_key, key, parts, value in _prefixed_variables(env, prefix, separator):
        if _addresses_config(parts, config_flag):
            # File pointers: ordered by the pipeline, which loads them.
            _refuse_root_config_append(orig_key, parts, separator)
            _handle_env_config_flag(parts, target, env_configs, value, union_tag, orig_key)
            continue
        variables.append((_env_order(parts, key, walk_target, union_tag), orig_key, key, parts, value))

    # The environment has no typing order, so it is given one: the broader variable first.
    for _, orig_key, key, parts, value in sorted(variables):
        _refuse_reserved_key(orig_key, parts)
        if _apply_env_json_cast(orig_key, parts, walk_target, value, data, root_json, union_tag, is_struct=is_struct):
            continue

        if not is_struct and not key:
            # The bare prefix sets a non-struct root whole, as the bare --<cli_prefix> does.
            data[_defaults.ROOT_KEY] = _try_coerce(_resolve_type(target), _StrToken(value))
            continue

        # A delete or an append is checked as the value variable of its path is (BUG-182).
        is_delete, is_append = _is_env_delete(parts), _is_env_append(parts)
        spelled = [*parts[:-1], parts[-1][:-1]] if is_delete or is_append else parts
        path, ft = _resolve_env_parts(walk_target, spelled, union_tag)
        # Locals are not target fields: skip the unknown-field warning and store the raw
        # token; _pipeline checks and coerces them (docs-dev/architecture/locals.md).
        is_locals = _locals_segment_index(target, path, union_tag) is not None
        if not is_locals and _warn_unknown_env_field(orig_key, path, target, walk_target, union_tag):
            continue
        if is_locals:
            ft = None
        else:
            _refuse_below_a_sequence(orig_key, path, walk_target, union_tag)
        if is_delete:
            _handle_env_delete(orig_key, path, data, walk_target, union_tag)
            continue

        # Same rule as the CLI: a bare callable shorthand already stored at a prefix of
        # this path is a spec this variable refines, not a scalar it replaces.
        _open_callable_shorthand(data, path, walk_target, union_tag)
        _restart_restated_node(data, path, walk_target, union_tag)
        if is_append:
            # One value, read as the flag's single token is: a JSON array is several items.
            et = _appended_element_type(walk_target, path, union_tag, orig_key, ft)
            _write_append(data, path, _collect_append_items([_EqValue(value)], 0, et, orig_key)[0])
            continue
        _store_env_value(path, ft, value, data, orig_key)

    from confarg._typed_merge import merge_root  # noqa: PLC0415  # import cycle: it walks types with _parse_cli

    return fold_root_json(data, root_json, merge_root(target, union_tag)), env_configs

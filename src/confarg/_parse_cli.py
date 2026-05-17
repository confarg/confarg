# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI argument parsing for confarg."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from confarg._errors import ConfargError, UnknownArgumentError
from confarg._merge import (
    DICT_DELETE,
    LIST_APPEND_KEY,
    LIST_DELETE_KEY,
    LIST_POST_APPEND_DELETE_KEY,
    LIST_REPLACE_BASE_KEY,
    _accumulate_list_delete,
    _set_nested,
)
from confarg._types import (
    _dict_kv,
    _elem_type,
    _is_callable,
    _is_dc,
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


def _subclass_field_type(tp: type, field: str) -> Any | None:
    """Search all dataclass subclasses of tp for a field, returning its type.

    Returns the common type if all subclasses agree, str if they disagree, None if absent.
    """
    found: list[Any] = []
    queue = list(tp.__subclasses__())
    while queue:
        sub = queue.pop()
        queue.extend(sub.__subclasses__())
        if not _is_struct(sub):
            continue
        flds = _struct_fields(sub)
        if field in flds:
            found.append(flds[field])
    if not found:
        return None
    first = found[0]
    return first if all(f == first for f in found[1:]) else str


def _resolve_field_type(target: Any, parts: list[str], union_tag: str) -> Any | None:
    """Walk the type tree following dot-separated path parts.

    Resolves the type at the end of the path by traversing dataclass fields,
    collections, dicts, and unions.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The resolved type at the end of the path, or None if the path is invalid.
    """
    tp = _resolve_type(target)
    for idx, part in enumerate(parts):
        if part == union_tag:
            return str
        tp = _resolve_type(tp)
        if _is_union(tp):
            remaining = parts[idx:]
            resolved = []
            for variant in _union_args_no_none(tp):
                v = _resolve_type(variant)
                result = _resolve_field_type(v, remaining, union_tag)
                if result is not None:
                    resolved.append(result)
            if not resolved:
                return None
            first = resolved[0]
            if all(r == first for r in resolved[1:]):
                return first  # All variants agree → safe to use
            return str  # Variants disagree → conservative string consumption
        elif _is_struct(tp):
            flds = _struct_fields(tp)
            if part in flds:
                tp = flds[part]
            else:
                tp = _subclass_field_type(tp, part)
                if tp is None:
                    return None
        elif _is_list(tp) or _is_set(tp) or _is_frozenset(tp):
            tp = _elem_type(tp)
        elif _is_tuple(tp):
            et = _tuple_types(tp)
            if et is None:
                tp = _elem_type(tp)
            else:
                try:
                    tp = et[int(part)]
                except (ValueError, IndexError):
                    return None
        elif _is_dict(tp):
            _, vt = _dict_kv(tp)
            tp = vt
        elif _is_callable(tp):
            if part in ("fn", "class", "call"):
                tp = str
            elif part == "bind":
                remaining_count = len(parts) - idx - 1
                if remaining_count == 0:
                    return None  # --field.bind alone is not addressable
                return str  # --field.bind.key -> str leaf
            else:
                # Accept flat constructor kwargs for both factory mode and callable-object mode.
                return str
        else:
            return None
    return tp


def _is_dict_at_path(target: Any, parts: list[str], union_tag: str) -> bool:
    """Check if any prefix of the path lands on a dict type.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to check.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        True if any non-empty prefix of parts resolves to a dict type.
    """
    for j in range(len(parts) - 1, 0, -1):
        pt = _resolve_field_type(target, parts[:j], union_tag)
        if pt is not None and _is_dict(_resolve_type(pt)):
            return True
    return False


def _parse_json_arg(token: str, flag: str) -> Any:
    """Parse token as JSON, raising ConfargError on invalid JSON.

    Args:
        token: The raw CLI token to parse.
        flag: The flag name (e.g. ``--foo``) used in the error message.

    Returns:
        The decoded JSON value.

    Raises:
        ConfargError: If the token is not valid JSON.
    """
    try:
        return json.loads(token)
    except json.JSONDecodeError as e:
        raise ConfargError(f"Invalid JSON for {flag}: {e}") from e


def _looks_like_flag(token: str) -> bool:
    """Check whether a token looks like a CLI flag (--word).

    Bare ``--`` and negative numbers like ``--3.14`` are not considered flags.

    Args:
        token: The CLI token to check.

    Returns:
        True if the token looks like a CLI flag.
    """
    return token.startswith("--") and len(token) > 2 and not token[2:].lstrip("-").replace(".", "").isdigit()


def _next_is_flag_or_end(args: Sequence[str], i: int) -> bool:
    """Check whether the next position is past the end or is a flag.

    Args:
        args: The CLI argument sequence.
        i: The index to check.

    Returns:
        True if index i is past the end of args or args[i] looks like a flag.
    """
    return i >= len(args) or _looks_like_flag(args[i])


def _check_config_flag_conflict(target: Any, config_flag: str, cli_prefix: str) -> None:
    """Raise ConfargError if config_flag matches a top-level field name of target.

    When config_flag shadows a field name the user can never set that field via
    --{config_flag}, because the parser intercepts it as a file-path argument.
    """
    flag_display = f"--{cli_prefix}.{config_flag}" if cli_prefix else f"--{config_flag}"

    def _check_struct(tp: Any) -> None:
        flds = _struct_fields(tp)
        if config_flag in flds:
            tp_name = getattr(tp, "__name__", repr(tp))
            raise ConfargError(
                f"{flag_display!r} is reserved as the config-file flag but {tp_name} has a field"
                f" named {config_flag!r}. The field cannot be set via CLI because the flag is"
                f" intercepted before field lookup."
                f" Pass a different config_flag to merge()/load(), e.g. config_flag='conf'."
            )

    tp = _resolve_type(target)
    if _is_struct(tp):
        _check_struct(tp)
    elif _is_union(tp):
        for variant in _union_args_no_none(tp):
            v = _resolve_type(variant)
            if _is_struct(v):
                _check_struct(v)


def _parse_cli(
    args: Sequence[str],
    target: Any,
    cli_prefix: str,
    config_flag: str,
    union_tag: str,
) -> tuple[dict[str, Any], list[tuple[str, Path]]]:
    """Parse CLI arguments into a nested dict and a list of config file paths.

    Args:
        args: The CLI argument sequence to parse.
        target: The target type, used for type-aware parsing decisions.
        cli_prefix: Required prefix for CLI flags (empty string for no prefix).
        config_flag: The flag name used to specify config files.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        A tuple of (data_dict, config_files) where data_dict is the parsed
        argument data and config_files is a list of (subpath, Path) pairs.

    Raises:
        UnknownArgumentError: If an unrecognized argument is encountered.
        ConfargError: If a config flag is missing its path argument or conflicts with a field name.
    """
    # Detect config_flag shadowing a field name before parsing begins.
    _check_config_flag_conflict(target, config_flag, cli_prefix)

    # Normalize --key=value into --key value so the rest of the parser is uniform.
    normalized: list[str] = []
    for tok in args:
        if tok.startswith("--") and "=" in tok:
            flag, _, val = tok.partition("=")
            normalized.append(flag)
            normalized.append(val)
        else:
            normalized.append(tok)
    args = normalized

    data: dict[str, Any] = {}
    config_files: list[tuple[str, Path]] = []
    target_r = _resolve_type(target)
    is_struct = _is_struct_like(target_r)
    i = 0

    while i < len(args):
        token = args[i]
        if not _looks_like_flag(token):
            raise UnknownArgumentError(
                f"Unexpected positional argument: {token!r}."
                " All arguments must be named flags (e.g. --fieldname value)."
            )

        raw_key = token[2:]

        # Strip cli_prefix
        key = raw_key
        if cli_prefix:
            dot_pfx = cli_prefix + "."
            if key.startswith(dot_pfx):
                key = key[len(dot_pfx) :]
            elif key == cli_prefix:
                key = ""
            else:
                raise UnknownArgumentError(
                    f"Unknown argument: {token!r}. Expected arguments to start with --{cli_prefix}."
                )

        # Config flag
        if key == config_flag or key.startswith(config_flag + "."):
            subpath = key[len(config_flag) + 1 :] if key.startswith(config_flag + ".") else ""
            i += 1
            if i >= len(args) or _looks_like_flag(args[i]):
                raise ConfargError(
                    f"Missing file path after --{config_flag}. Usage: --{config_flag} /path/to/config.yaml"
                )
            while i < len(args) and not _looks_like_flag(args[i]):
                config_files.append((subpath, Path(args[i])))
                i += 1
            continue

        path = key.split(".") if key else []

        # Detect + suffix on last path segment (list append): --foo.bar+
        # len > 1 guard prevents bare "--+" or "--foo.+" from triggering append mode.
        append_mode = bool(path) and path[-1].endswith("+") and len(path[-1]) > 1
        if append_mode:
            path[-1] = path[-1][:-1]

        # Detect - suffix on last path segment (deletion): --foo.bar- or --foo.1-
        # len > 1 guard prevents bare "--foo.-" from triggering delete mode.
        delete_mode = not append_mode and bool(path) and path[-1].endswith("-") and len(path[-1]) > 1
        if delete_mode:
            raw_last = path[-1][:-1]
            path[-1] = raw_last
            try:
                delete_idx = int(raw_last)
                is_list_delete = True
            except ValueError:
                is_list_delete = False
                delete_idx = -1  # unused

        # .str type-cast: --foo.str VALUE forces VALUE as a plain string (bypasses steal rule)
        force_str = not delete_mode and bool(path) and path[-1] == "str"
        if force_str:
            path = path[:-1]

        # Delete mode: --foo.bar- (dict-key deletion) or --foo.1- (list-index deletion)
        if delete_mode:
            if is_list_delete:
                parent_path = path[:-1]
                # Validate the parent path is reachable (use the numeric-index path for type look-up).
                ft_check = _resolve_field_type(target, path, union_tag)
                if ft_check is None and not _is_dict_at_path(target, path, union_tag):
                    raise UnknownArgumentError(
                        f"Unknown argument: {token!r} (field '{'.'.join(parent_path)}' not found or not indexable)"
                    )
                # If there's already an append op at this path, this delete applies to the
                # post-append list; use LIST_POST_APPEND_DELETE_KEY so _apply_list_ops
                # executes it after the appends rather than before.
                node: Any = data
                for _p in parent_path:
                    if isinstance(node, dict) and _p in node:
                        node = node[_p]
                    else:
                        node = {}
                        break
                has_append = isinstance(node, dict) and LIST_APPEND_KEY in node
                del_key = LIST_POST_APPEND_DELETE_KEY if has_append else LIST_DELETE_KEY
                _accumulate_list_delete(data, parent_path, delete_idx, token, delete_key=del_key)
            else:
                # Dict-key (or struct-field) deletion.
                ft_check = _resolve_field_type(target, path, union_tag)
                if ft_check is None and not _is_dict_at_path(target, path, union_tag):
                    raise UnknownArgumentError(f"Unknown argument: {token!r} (field '{'.'.join(path)}' not found)")
                _set_nested(data, path, DICT_DELETE)
            i += 1
            continue

        # Non-dataclass scalar target with empty path
        if not is_struct and not path:
            i += 1
            if i >= len(args) or _looks_like_flag(args[i]):
                raise ConfargError(f"Missing value for {token!r}. Usage: {token} <value>")
            data["__root__"] = _try_coerce(target_r, _StrToken(args[i]))
            i += 1
            continue

        # Resolve type at this path
        ft = _resolve_field_type(target, path, union_tag)

        if ft is None:
            if append_mode:
                raise UnknownArgumentError(f"Unknown argument: {token} (field '{'.'.join(path)}' not found)")
            if _is_dict_at_path(target, path, union_tag):
                i += 1
                if i < len(args) and not _looks_like_flag(args[i]):
                    _set_nested(data, path, _StrToken(args[i]))
                    i += 1
                continue
            if len(path) > 1 and path[-1] in ("", "+"):
                dot_pos = token.rfind(".")
                raise UnknownArgumentError(f"Missing field name after '{token[: dot_pos + 1]}'")
            raise UnknownArgumentError(f"Unknown argument: {token} (field '{'.'.join(path)}' not found)")

        ft = _resolve_type(ft)
        i += 1  # move past the flag token

        # .str cast: store next token as a plain str (bypasses steal rule in construct)
        if force_str:
            if i >= len(args) or _looks_like_flag(args[i]):
                raise ConfargError(f"Missing value for {token!r}. Usage: {token} <value>")
            _set_nested(data, path, str(args[i]))
            i += 1
            continue

        # List/set/frozenset append mode (--foo+): collect values, store as {"+": [...]}
        if append_mode:
            if not _is_varlen_collection(ft):
                raise ConfargError(
                    f"Cannot use + (append) syntax on {token!r}:"
                    f" field '{'.'.join(path)}' has type {ft!r}, which is not a list, set, or frozenset."
                )
            et = _elem_type(ft)
            append_items: list[Any] = []
            consumed_json = False
            if i < len(args) and not _looks_like_flag(args[i]) and args[i].startswith("["):
                try:
                    parsed = json.loads(args[i])
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    append_items = parsed
                    i += 1
                    consumed_json = True
            if not consumed_json:
                # Space-separated values; JSON objects are treated as single elements
                while i < len(args) and not _looks_like_flag(args[i]):
                    tok = args[i]
                    if tok.startswith("{"):
                        try:
                            append_items.append(json.loads(tok))
                        except json.JSONDecodeError:
                            append_items.append(_try_coerce(et, _StrToken(tok)))
                    else:
                        append_items.append(_try_coerce(et, _StrToken(tok)))
                    i += 1
            # Combine with any prior operation on this path, preserving ordering semantics.
            node = data
            for p in path[:-1]:
                node = node.get(p, {}) if isinstance(node, dict) else {}
            existing = node.get(path[-1]) if path and isinstance(node, dict) else None

            if isinstance(existing, list):
                # Prior full-replace at this path; keep it as the new base so the
                # reset is not lost when _deep_merge applies the config list.
                new_val: dict[str, Any] = {LIST_REPLACE_BASE_KEY: existing, LIST_APPEND_KEY: append_items}
            elif isinstance(existing, dict):
                if LIST_REPLACE_BASE_KEY in existing:
                    # Already has an explicit base; accumulate appends.
                    prior = existing.get(LIST_APPEND_KEY, [])
                    new_val = {**existing, LIST_APPEND_KEY: prior + append_items}
                elif LIST_APPEND_KEY in existing:
                    # Prior append without an explicit base; accumulate.
                    new_val = {**existing, LIST_APPEND_KEY: existing[LIST_APPEND_KEY] + append_items}
                else:
                    # Has delete spec and/or index patches; add append alongside.
                    new_val = {**existing, LIST_APPEND_KEY: append_items}
            else:
                new_val = {LIST_APPEND_KEY: append_items}
            _set_nested(data, path, new_val)
            continue

        # JSON object for dataclass / dict / callable / union-with-dc fields
        if i < len(args) and not _looks_like_flag(args[i]) and args[i].startswith("{"):
            accepts_obj = (
                _is_dc(ft)
                or _is_dict(ft)
                or _is_callable(ft)
                or (_is_union(ft) and any(_is_dc(_resolve_type(v)) for v in _union_args_no_none(ft)))
            )
            if accepts_obj:
                _set_nested(data, path, _parse_json_arg(args[i], token))
                i += 1
                continue

        # Dataclass field with no value → skip (use defaults)
        if _is_dc(ft) and _next_is_flag_or_end(args, i):
            continue

        # JSON array for list / tuple / union-of-tuples fields
        is_collection = (
            _is_varlen_collection(ft)
            or _is_tuple(ft)
            or (_is_union(ft) and (nv := _union_args_no_none(ft)) and all(_is_tuple(_resolve_type(v)) for v in nv))
        )
        if is_collection and i < len(args) and not _looks_like_flag(args[i]) and args[i].startswith("["):
            try:
                parsed = json.loads(args[i])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                _set_nested(data, path, parsed)
                i += 1
                continue

        # Variable-length collection → consume until next flag
        if _is_varlen_collection(ft):
            et = _elem_type(ft)
            items: list[Any] = []
            while i < len(args) and not _looks_like_flag(args[i]):
                items.append(_try_coerce(et, _StrToken(args[i])))
                i += 1
            _set_nested(data, path, items)
            continue

        # Fixed-length tuple → consume exact count
        if _is_tuple(ft):
            tt = _tuple_types(ft)
            if tt is not None:
                items = []
                for et in tt:
                    if i < len(args):
                        items.append(_try_coerce(et, _StrToken(args[i])))
                        i += 1
                _set_nested(data, path, items)
                continue

        # Union of tuple variants → consume greedily (disambiguation at construct time)
        if _is_union(ft):
            non_none_vars = _union_args_no_none(ft)
            if non_none_vars and all(_is_tuple(_resolve_type(v)) for v in non_none_vars):
                items = []
                while i < len(args) and not _looks_like_flag(args[i]):
                    items.append(_StrToken(args[i]))
                    i += 1
                _set_nested(data, path, items)
                continue

        # Default: consume one value
        if i >= len(args) or _looks_like_flag(args[i]):
            raise ConfargError(f"Missing value for {token!r}. Usage: {token} <value>")
        _set_nested(data, path, _try_coerce(ft, _StrToken(args[i])))
        i += 1

    return data, config_files

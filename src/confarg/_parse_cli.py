# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI argument parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    _dataclass_subclasses,
    _dict_kv,
    _elem_type,
    _is_callable,
    _is_dc,
    _is_dict,
    _is_frozenset,
    _is_list,
    _is_namedtuple,
    _is_set,
    _is_struct,
    _is_struct_like,
    _is_tuple,
    _is_union,
    _is_varlen_collection,
    _namedtuple_fields,
    _Pinned,
    _resolve_type,
    _StrToken,
    _struct_fields,
    _tuple_types,
    _union_args_no_none,
)
from confarg.exceptions import ConfargError, UnknownArgumentError
from confarg.typedload._coerce import _try_coerce

_SCALAR_CAST_NAMES: frozenset[str] = frozenset({"str", "int", "float", "bool"})
_CAST_TYPES: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}


def _subclass_field_type(tp: type, field: str) -> Any | None:
    """Search all dataclass subclasses of tp for a field, returning its type.

    Returns the common type if all subclasses agree, str if they disagree, None if absent.
    """
    found: list[Any] = []
    for sub in _dataclass_subclasses(tp):
        flds = _struct_fields(sub)
        if field in flds:
            found.append(flds[field])
    if not found:
        return None
    first = found[0]
    return first if all(f == first for f in found[1:]) else str


def _resolve_union_field_type(tp: Any, remaining: list[str], union_tag: str) -> Any | None:
    """Resolve the field type through a Union by trying all non-None variants."""
    resolved = []
    for variant in _union_args_no_none(tp):
        v = _resolve_type(variant)
        result = _resolve_field_type(v, remaining, union_tag)
        if result is not None:
            resolved.append(result)
    if not resolved:
        return None
    first = resolved[0]
    return first if all(r == first for r in resolved[1:]) else str


def _step_tuple_type(tp: Any, part: str) -> Any | None:
    """Advance one step into a tuple type by numeric index."""
    et = _tuple_types(tp)
    if et is None:
        return _elem_type(tp)
    try:
        return et[int(part)]
    except (ValueError, IndexError):
        return None


def _advance_field_type(tp: Any, part: str) -> Any | None:  # noqa: PLR0911
    """Advance one step into tp along path segment part. Returns new type or None."""
    if _is_namedtuple(tp):
        flds = _namedtuple_fields(tp)
        if part in flds:
            return flds[part]
        try:
            return list(flds.values())[int(part)]
        except (ValueError, IndexError):
            return None
    if _is_struct(tp):
        flds = _struct_fields(tp)
        return flds[part] if part in flds else _subclass_field_type(tp, part)
    if _is_list(tp) or _is_set(tp) or _is_frozenset(tp):
        return _elem_type(tp)
    if _is_tuple(tp):
        return _step_tuple_type(tp, part)
    if _is_dict(tp):
        _, vt = _dict_kv(tp)
        return vt
    if _is_callable(tp):
        # "fn"/"class"/"call" are recognized sub-keys; flat kwargs also accepted
        return str
    return None


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
            return _resolve_union_field_type(tp, parts[idx:], union_tag)
        if _is_callable(tp) and part == "bind":
            # --field.bind alone is not addressable; --field.bind.key → str leaf
            return None if len(parts) - idx - 1 == 0 else str
        tp = _advance_field_type(tp, part)
        if tp is None:
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
        msg = f"Invalid JSON for {flag}: {e}"
        raise ConfargError(msg) from e


def _looks_like_flag(token: str) -> bool:
    """Check whether a token looks like a CLI flag (--word).

    A flag must start with ``--`` followed by a letter or underscore. Bare
    ``--`` and tokens like ``--:`` or ``--3`` are not flags.

    Args:
        token: The CLI token to check.

    Returns:
        True if the token looks like a CLI flag.
    """
    _double_dash = "--"
    return (
        token.startswith(_double_dash)
        and len(token) > len(_double_dash)
        and (token[len(_double_dash)].isalpha() or token[len(_double_dash)] == "_")
    )


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
            msg = (
                f"{flag_display!r} is reserved as the config-file flag but {tp_name} has a field"
                f" named {config_flag!r}. The field cannot be set via CLI because the flag is"
                f" intercepted before field lookup."
                f" Pass a different config_flag to merge()/load(), e.g. config_flag='conf'."
            )
            raise ConfargError(msg)

    tp = _resolve_type(target)
    if _is_struct(tp):
        _check_struct(tp)
    elif _is_union(tp):
        for variant in _union_args_no_none(tp):
            v = _resolve_type(variant)
            if _is_struct(v):
                _check_struct(v)


# ---------------------------------------------------------------------------
# Helpers for the main parse loop
# ---------------------------------------------------------------------------


def _normalize_eq_args(args: Sequence[str]) -> list[str]:
    """Split --key=value tokens into --key value pairs."""
    normalized: list[str] = []
    for tok in args:
        if tok.startswith("--") and "=" in tok:
            flag, _, val = tok.partition("=")
            normalized.append(flag)
            normalized.append(val)
        else:
            normalized.append(tok)
    return normalized


def _strip_cli_prefix(raw_key: str, cli_prefix: str, token: str) -> str:
    """Return raw_key with cli_prefix stripped, or raise UnknownArgumentError."""
    if not cli_prefix:
        return raw_key
    dot_pfx = f"{cli_prefix}."
    if raw_key.startswith(dot_pfx):
        return raw_key[len(dot_pfx) :]
    if raw_key == cli_prefix:
        return ""
    msg = f"Unknown argument: {token!r}. Expected arguments to start with --{cli_prefix}."
    raise UnknownArgumentError(msg)


def _consume_config_paths(args: list[str], i: int, key: str, config_flag: str) -> tuple[int, list[tuple[str, Path]]]:
    """Consume file-path tokens for a --config[.subpath] flag.

    Returns (new_i, [(subpath, Path)]).
    """
    subpath = key[len(config_flag) + 1 :] if key.startswith(config_flag + ".") else ""
    i += 1
    if i >= len(args) or _looks_like_flag(args[i]):
        msg = f"Missing file path after --{config_flag}. Usage: --{config_flag} /path/to/config.yaml"
        raise ConfargError(msg)
    pairs: list[tuple[str, Path]] = []
    while i < len(args) and not _looks_like_flag(args[i]):
        pairs.append((subpath, Path(args[i])))
        i += 1
    return i, pairs


def _parse_flag_mode(
    key: str,
) -> tuple[list[str], bool, bool, str | None, int, bool]:
    """Decode mode flags from a flag key.

    Returns ``(path, append_mode, delete_mode, force_cast, delete_idx, is_list_delete)``.
    ``force_cast`` is one of ``"str"``, ``"int"``, ``"float"``, ``"bool"``, or ``None``.
    """
    path = key.split(".") if key else []

    append_mode = bool(path) and path[-1].endswith("+") and len(path[-1]) > 1
    if append_mode:
        path[-1] = path[-1][:-1]

    delete_mode = not append_mode and bool(path) and path[-1].endswith("-") and len(path[-1]) > 1
    delete_idx = -1
    is_list_delete = False
    if delete_mode:
        raw_last = path[-1][:-1]
        path[-1] = raw_last
        try:
            delete_idx = int(raw_last)
            is_list_delete = True
        except ValueError:
            pass

    force_cast: str | None = None
    if not delete_mode and bool(path) and path[-1] in _SCALAR_CAST_NAMES:
        force_cast = path.pop()

    return path, append_mode, delete_mode, force_cast, delete_idx, is_list_delete


@dataclass
class _ParseCtx:
    """Shared parse-loop state threaded through token handlers."""

    argv: Sequence[str]
    target: Any
    union_tag: str
    data: dict[str, Any] = field(default_factory=dict)


def _handle_delete_token(
    ctx: _ParseCtx,
    token: str,
    path: list[str],
    *,
    is_list_delete: bool,
    delete_idx: int,
) -> None:
    """Apply a delete-mode flag (--foo.1- or --foo.bar-) to data."""
    if is_list_delete:
        parent_path = path[:-1]
        ft_check = _resolve_field_type(ctx.target, path, ctx.union_tag)
        if ft_check is None and not _is_dict_at_path(ctx.target, path, ctx.union_tag):
            msg = f"Unknown argument: {token!r} (field '{'.'.join(parent_path)}' not found or not indexable)"
            raise UnknownArgumentError(msg)
        node: Any = ctx.data
        for _p in parent_path:
            node = node[_p] if isinstance(node, dict) and _p in node else {}
        del_key = LIST_POST_APPEND_DELETE_KEY if isinstance(node, dict) and LIST_APPEND_KEY in node else LIST_DELETE_KEY
        _accumulate_list_delete(ctx.data, parent_path, delete_idx, token, delete_key=del_key)
    else:
        ft_check = _resolve_field_type(ctx.target, path, ctx.union_tag)
        if ft_check is None and not _is_dict_at_path(ctx.target, path, ctx.union_tag):
            msg = f"Unknown argument: {token!r} (field '{'.'.join(path)}' not found)"
            raise UnknownArgumentError(msg)
        _set_nested(ctx.data, path, DICT_DELETE)


def _collect_append_items(args: Sequence[str], i: int, et: Any) -> tuple[list[Any], int]:
    """Collect append-mode values from args, returning (items, new_i).

    Accepts a JSON array literal as a single token, otherwise consumes space-separated
    tokens until the next flag.
    """
    if i < len(args) and not _looks_like_flag(args[i]) and args[i].startswith("["):
        try:
            parsed = json.loads(args[i])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return parsed, i + 1

    items: list[Any] = []
    while i < len(args) and not _looks_like_flag(args[i]):
        tok = args[i]
        if tok.startswith("{"):
            try:
                items.append(json.loads(tok))
            except json.JSONDecodeError:
                items.append(_try_coerce(et, _StrToken(tok)))
        else:
            items.append(_try_coerce(et, _StrToken(tok)))
        i += 1
    return items, i


def _merge_append_ops(existing: Any, append_items: list[Any]) -> dict[str, Any]:
    """Combine append_items with any existing list-operation dict at this path."""
    if isinstance(existing, list):
        return {LIST_REPLACE_BASE_KEY: existing, LIST_APPEND_KEY: append_items}
    if isinstance(existing, dict):
        if LIST_REPLACE_BASE_KEY in existing:
            prior = existing.get(LIST_APPEND_KEY, [])
            return {**existing, LIST_APPEND_KEY: prior + append_items}
        if LIST_APPEND_KEY in existing:
            return {**existing, LIST_APPEND_KEY: existing[LIST_APPEND_KEY] + append_items}
        return {**existing, LIST_APPEND_KEY: append_items}
    return {LIST_APPEND_KEY: append_items}


def _handle_append_token(
    ctx: _ParseCtx,
    i: int,
    token: str,
    ft: Any,
    path: list[str],
) -> int:
    """Process an append-mode flag (--foo+ items...) and return the new arg index."""
    if not _is_varlen_collection(ft):
        msg = (
            f"Cannot use + (append) syntax on {token!r}:"
            f" field '{'.'.join(path)}' has type {ft!r}, which is not a list, set, or frozenset."
        )
        raise ConfargError(msg)
    et = _elem_type(ft)
    append_items, i = _collect_append_items(ctx.argv, i, et)
    node: Any = ctx.data
    for p in path[:-1]:
        node = node.get(p, {}) if isinstance(node, dict) else {}
    existing = node.get(path[-1]) if path and isinstance(node, dict) else None
    _set_nested(ctx.data, path, _merge_append_ops(existing, append_items))
    return i


def _consume_fixed_tuple_args(args: Sequence[str], i: int, tt: list[Any], path: list[str], data: dict[str, Any]) -> int:
    """Consume exactly len(tt) arguments for a fixed-length tuple field."""
    items: list[Any] = []
    for et in tt:
        if i < len(args):
            items.append(_try_coerce(et, _StrToken(args[i])))
            i += 1
    _set_nested(data, path, items)
    return i


def _consume_union_tuple_args(args: Sequence[str], i: int, path: list[str], data: dict[str, Any]) -> int:
    """Consume greedy space-separated args for a union-of-tuples field."""
    items: list[Any] = []
    while i < len(args) and not _looks_like_flag(args[i]):
        items.append(_StrToken(args[i]))
        i += 1
    _set_nested(data, path, items)
    return i


def _handle_scalar_root(args: list[str], i: int, token: str, target_r: Any, data: dict[str, Any]) -> int:
    """Consume the single value for a non-struct scalar target. Returns new arg index."""
    i += 1
    if i >= len(args) or _looks_like_flag(args[i]):
        msg = f"Missing value for {token!r}. Usage: {token} <value>"
        raise ConfargError(msg)
    data["__root__"] = _try_coerce(target_r, _StrToken(args[i]))
    return i + 1


def _handle_force_cast(  # noqa: PLR0913  # cast_name is a necessary discriminator, not incidental
    args: list[str],
    i: int,
    token: str,
    data: dict[str, Any],
    path: list[str],
    cast_name: str,
) -> int:
    """Consume the value for a .<type>-cast flag, storing it as _Pinned. Returns new arg index."""
    if i >= len(args) or _looks_like_flag(args[i]):
        msg = f"Missing value for {token!r}. Usage: {token} <value>"
        raise ConfargError(msg)
    _set_nested(data, path, _Pinned(_CAST_TYPES[cast_name], _StrToken(args[i])))
    return i + 1


def _handle_unknown_field(
    ctx: _ParseCtx,
    i: int,
    token: str,
    path: list[str],
    *,
    append_mode: bool,
) -> int:
    """Handle a flag whose field path could not be resolved.

    For dict-typed paths, consumes an optional value and returns the new index.
    Otherwise always raises UnknownArgumentError.
    """
    if append_mode:
        msg = f"Unknown argument: {token} (field '{'.'.join(path)}' not found)"
        raise UnknownArgumentError(msg)
    if _is_dict_at_path(ctx.target, path, ctx.union_tag):
        i += 1
        if i < len(ctx.argv) and not _looks_like_flag(ctx.argv[i]):
            _set_nested(ctx.data, path, _StrToken(ctx.argv[i]))
            i += 1
        return i
    if len(path) > 1 and path[-1] in ("", "+"):
        dot_pos = token.rfind(".")
        msg = f"Missing field name after '{token[: dot_pos + 1]}'"
        raise UnknownArgumentError(msg)
    msg = f"Unknown argument: {token} (field '{'.'.join(path)}' not found)"
    raise UnknownArgumentError(msg)


def _try_parse_json_list(arg: str) -> list[Any] | None:
    """Parse arg as a JSON array and return it, or None if not valid JSON or not a list."""
    try:
        parsed = json.loads(arg)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _consume_collection_or_scalar(
    ctx: _ParseCtx,
    i: int,
    token: str,
    ft: Any,
    path: list[str],
) -> int:
    """Consume collection (array/tuple/varlen) or scalar value; return new arg index."""
    args = ctx.argv
    # JSON array → list / tuple / union-of-tuples
    is_collection = (
        _is_varlen_collection(ft)
        or _is_tuple(ft)
        or (_is_union(ft) and (nv := _union_args_no_none(ft)) and all(_is_tuple(_resolve_type(v)) for v in nv))
    )
    if (
        is_collection
        and i < len(args)
        and not _looks_like_flag(args[i])
        and args[i].startswith("[")
        and (parsed := _try_parse_json_list(args[i])) is not None
    ):
        _set_nested(ctx.data, path, parsed)
        return i + 1

    # Variable-length collection → consume until the next flag
    if _is_varlen_collection(ft):
        et = _elem_type(ft)
        items: list[Any] = []
        while i < len(args) and not _looks_like_flag(args[i]):
            items.append(_try_coerce(et, _StrToken(args[i])))
            i += 1
        _set_nested(ctx.data, path, items)
        return i

    # Fixed-length tuple → consume exact count
    if _is_tuple(ft):
        tt = _tuple_types(ft)
        if tt is not None:
            return _consume_fixed_tuple_args(args, i, tt, path, ctx.data)

    # Union of tuple variants → consume greedily (disambiguation deferred to construct)
    if _is_union(ft):
        non_none_vars = _union_args_no_none(ft)
        if non_none_vars and all(_is_tuple(_resolve_type(v)) for v in non_none_vars):
            return _consume_union_tuple_args(args, i, path, ctx.data)

    # Default: consume one scalar value
    if i >= len(args) or _looks_like_flag(args[i]):
        msg = f"Missing value for {token!r}. Usage: {token} <value>"
        raise ConfargError(msg)
    _set_nested(ctx.data, path, _try_coerce(ft, _StrToken(args[i])))
    return i + 1


def _consume_typed_arg(
    ctx: _ParseCtx,
    i: int,
    token: str,
    ft: Any,
    path: list[str],
) -> int:
    """Consume the value(s) for a resolved, non-append field type and return the new arg index."""
    args = ctx.argv
    # JSON object → dataclass / dict / callable / union-with-dc
    if i < len(args) and not _looks_like_flag(args[i]) and args[i].startswith("{"):
        accepts_obj = (
            _is_dc(ft)
            or _is_dict(ft)
            or _is_callable(ft)
            or (_is_union(ft) and any(_is_dc(_resolve_type(v)) for v in _union_args_no_none(ft)))
        )
        if accepts_obj:
            _set_nested(ctx.data, path, _parse_json_arg(args[i], token))
            return i + 1

    # Dataclass flag with no value → use defaults
    if _is_dc(ft) and _next_is_flag_or_end(args, i):
        return i

    return _consume_collection_or_scalar(ctx, i, token, ft, path)


def _parse_cli(
    argv: Sequence[str],
    target: Any,
    cli_prefix: str,
    config_flag: str,
    union_tag: str,
) -> tuple[dict[str, Any], list[tuple[str, Path]]]:
    """Parse CLI arguments into a nested dict and a list of config file paths.

    Args:
        argv: The CLI argument sequence to parse.
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
    _check_config_flag_conflict(target, config_flag, cli_prefix)
    argv = _normalize_eq_args(argv)

    ctx = _ParseCtx(argv=argv, target=target, union_tag=union_tag)
    config_files: list[tuple[str, Path]] = []
    target_r = _resolve_type(target)
    is_struct = _is_struct_like(target_r)
    i = 0

    while i < len(argv):
        token = argv[i]
        if not _looks_like_flag(token):
            msg = (
                f"Unexpected positional argument: {token!r}."
                " All arguments must be named flags (e.g. --fieldname value)."
            )
            raise UnknownArgumentError(msg)

        key = _strip_cli_prefix(token[2:], cli_prefix, token)

        if key == config_flag or key.startswith(config_flag + "."):
            i, new_cfgs = _consume_config_paths(argv, i, key, config_flag)
            config_files.extend(new_cfgs)
            continue

        path, append_mode, delete_mode, force_cast, delete_idx, is_list_delete = _parse_flag_mode(key)

        if delete_mode:
            _handle_delete_token(ctx, token, path, is_list_delete=is_list_delete, delete_idx=delete_idx)
            i += 1
            continue

        if not is_struct and not path:
            i = _handle_scalar_root(argv, i, token, target_r, ctx.data)
            continue

        ft = _resolve_field_type(target, path, union_tag)
        if ft is None:
            i = _handle_unknown_field(ctx, i, token, path, append_mode=append_mode)
            continue

        ft = _resolve_type(ft)
        i += 1

        if force_cast:
            i = _handle_force_cast(argv, i, token, ctx.data, path, force_cast)
            continue

        if append_mode:
            i = _handle_append_token(ctx, i, token, ft, path)
            continue

        i = _consume_typed_arg(ctx, i, token, ft, path)

    return ctx.data, config_files

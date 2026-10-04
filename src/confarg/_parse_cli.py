# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Vanilla command-line parsing, shaped by the target type.

Also hosts helpers shared with the env parser and the CLI adapters: the type walk,
force-cast detection, the local-variables name derivation, the ``--config`` scan and the
patch-only parse used by the adapters.

Dev Notes:
    docs-dev/architecture/cli-parsing/README.md
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

from confarg import _defaults
from confarg._callable import names_a_bind, names_an_opener, promote_bare_spec
from confarg._cast import FORCE_CAST_NAMES, JSON_CAST_NAME, fold_root_json, resolve_forced_value
from confarg._merge import (
    DICT_DELETE,
    LIST_APPEND_KEY,
    LIST_DELETE_KEY,
    LIST_POST_APPEND_DELETE_KEY,
    LIST_REPLACE_BASE_KEY,
    _accumulate_list_delete,
    _peek_nested,
    _set_nested,
)
from confarg._tags import import_tagged_classes
from confarg._types import (
    _dict_kv,
    _elem_type,
    _fixed_seq_types,
    _is_callable,
    _is_dict,
    _is_namedtuple,
    _is_struct,
    _is_struct_like,
    _is_union,
    _is_varlen_collection,
    _namedtuple_fields,
    _resolve_type,
    _StrToken,
    _struct_fields,
    _struct_member_names,
    _struct_member_type,
    _tuple_types,
    _union_args_no_none,
    _union_has_scalar_variant,
    _union_has_seq_variant,
    _union_has_varlen_variant,
    _UnionSeqToken,
)
from confarg.exceptions import ConfargError, UnknownArgumentError
from confarg.typedload._coerce import _try_coerce, _type_kind, _TypeKind


def _step_tuple_type(tp: Any, part: str) -> Any | None:
    """Advance one step into a tuple type by numeric index."""
    et = _tuple_types(tp)
    if et is None:
        return _elem_type(tp)
    try:
        return et[int(part)]
    except (ValueError, IndexError):
        return None


def _namedtuple_index_spellings(n: int) -> dict[str, int]:
    """Return every canonical index spelling for an n-field namedtuple, by position.

    The one source for "which index spellings exist" — str(i) and the negative str(i - n)
    that counts from the end (BUG-80) — so the type walk accepts exactly what
    cli/_build._collect_namedtuple_specs registers as flags (BUG-97).

    Dev Notes:
        docs-dev/architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md
    """
    return {**{str(i): i for i in range(n)}, **{str(i - n): i for i in range(n)}}


def _namedtuple_position_spellings(n: int, i: int) -> list[str]:
    """Return the index spellings of position i in an n-field namedtuple, str(i) first.

    The per-field view of :func:`_namedtuple_index_spellings`, for the registration and
    collection sites that list a field's keys rather than look one up.
    """
    return [spelled for spelled, pos in _namedtuple_index_spellings(n).items() if pos == i]


def _advance_field_type(tp: Any, part: str) -> Any | None:  # noqa: PLR0911  # one return per kind
    """Advance one step into tp along path segment part. Returns new type or None.

    Dispatches on :func:`~confarg.typedload._coerce._type_kind`, as construction does. A
    registered leaf with ``__init__`` parameters is walked as a struct: an explicit class
    tag may still open it.
    """
    match _type_kind(tp):
        case _TypeKind.NAMEDTUPLE:
            flds = _namedtuple_fields(tp)
            if part in flds:
                return flds[part]
            spellings = _namedtuple_index_spellings(len(flds))
            return list(flds.values())[spellings[part]] if part in spellings else None
        case _TypeKind.STRUCT | _TypeKind.TAGGABLE_LEAF:
            return _struct_member_type(tp, part)
        case _TypeKind.LIST | _TypeKind.SET | _TypeKind.FROZENSET:
            return _elem_type(tp)
        case _TypeKind.TUPLE:
            return _step_tuple_type(tp, part)
        case _TypeKind.DICT:
            _, vt = _dict_kv(tp)
            return vt
        case _TypeKind.CALLABLE:
            # "fn"/"class"/"call" are recognized sub-keys; flat kwargs also accepted
            return str
        case _TypeKind.ANY | _TypeKind.UNION | _TypeKind.LEAF:
            return None


def _field_types(target: Any, parts: list[str], union_tag: str, *, tag_fallback: bool = True) -> list[Any]:
    """Walk the type tree along *parts*, returning the type each union branch reaches.

    The one type walk. A union met before the path ends is walked once per non-None
    variant, so the answer lists one type per branch that accepts the whole path, in
    variant order; a branch that refuses it drops out, and an empty list means no branch
    accepts it. A path ending *on* a union-typed node answers that union, unexpanded.
    :func:`_resolve_field_type` folds the list into the single type a value is coerced
    by; a caller that asks what each branch holds at a node -- the env channel spelling
    the next segment -- reads it whole.

    A segment names the union tag only when no real member of that exact spelling exists
    at its position; a field named like the tag is that field.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.
        tag_fallback: Whether a segment no member reaches may still name the union tag.
            Off, the walk answers members only, which is how
            :func:`_names_tag_by_fallback` tells the two apart.
    """
    tp = _resolve_type(target)
    for idx, part in enumerate(parts):
        tp = _resolve_type(tp)
        if _is_union(tp):
            return [
                found
                for v in _union_args_no_none(tp)
                for found in _field_types(v, parts[idx:], union_tag, tag_fallback=tag_fallback)
            ]
        if _is_callable(tp) and names_a_bind(part):
            # A callable's bind key is addressable as a str-leaf subtree (--field.bind.key)
            # and, in escaped mode, as a plain scalar init-kwarg (--field.bind 5). Whether the
            # active-mode bind must be a dict is validated in construct, not here (lenient parse).
            return [str]
        if part in _locals_keys_nested(tp, union_tag):
            tp = dict[str, Any]
            continue
        tp = _advance_field_type(tp, part)
        if tp is None:
            if tag_fallback and part == union_tag:
                # The tag is the fallback, so it resolves only at a position no member
                # of its exact spelling reaches.
                return [str]
            return []
    return [tp]


def _resolve_field_type(target: Any, parts: list[str], union_tag: str, *, tag_fallback: bool = True) -> Any | None:
    """Return the type a value at the dotted path *parts* is coerced by, None if no branch accepts it.

    The fold of :func:`_field_types` over the branches that accept the path: their common
    type when they all agree, ``str`` -- the raw token, left for construction to read by
    the variant it picks -- when they do not.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.
        tag_fallback: Whether a segment no member reaches may still name the union tag.

    Returns:
        The resolved type at the end of the path, or None if the path is invalid.
    """
    found = _field_types(target, parts, union_tag, tag_fallback=tag_fallback)
    if not found:
        return None
    first = found[0]
    return first if all(t == first for t in found[1:]) else str


def _names_tag_by_fallback(target: Any, parts: list[str], union_tag: str) -> bool:
    """Return True if the path's last segment is the union tag, reached by the walk's fallback.

    The walk's own answer: the path resolves with the tag rule and does not without it,
    so a member spelled like the tag -- a field, a subclass-only field, a callable's
    directive -- is never mistaken for the tag.
    """
    return (
        bool(parts)
        and parts[-1] == union_tag
        and _resolve_field_type(target, parts, union_tag) is not None
        and _resolve_field_type(target, parts, union_tag, tag_fallback=False) is None
    )


def _addresses_callable_key(target: Any, parts: list[str], union_tag: str) -> bool:
    """Return True if the dotted path names a key *inside* a ``Callable`` field's spec.

    Everything below the field is one answer, because everything below it is one dict the
    parser writes verbatim: a directive, a bind subkey in either spelling, or a sibling
    kwarg no signature names.  Which of those a key *is* — and whether it is acceptable
    — the opener decides at construction, and a path does not see the opener.

    The adapters register a flag on this answer alone, so the caller must strip an
    append/delete suffix first: those flags are registered when typed, in the shape
    their mode demands.

    Dev Notes:
        docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
    """
    tp = _resolve_type(target)
    for idx, part in enumerate(parts):
        tp = _resolve_type(tp)
        if _is_union(tp):
            return any(_addresses_callable_key(v, parts[idx:], union_tag) for v in _union_args_no_none(tp))
        if _is_callable(tp):
            return True
        tp = _advance_field_type(tp, part)
        if tp is None:
            return False
    return False


def _is_collection_patch_path(target: Any, parts: list[str], union_tag: str) -> bool:
    """Return True if the dotted path indexes a list/tuple/set or keys a dict.

    Such paths (e.g. ``users.0``, ``dbs.1.port``, ``foo.bar``) are open-ended, so no
    static walk can list them: the adapters register their flags when argv types them.
    Pure struct-field, namedtuple, and callable paths return False.

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity
    """
    tp = _resolve_type(target)
    for idx, part in enumerate(parts):
        tp = _resolve_type(tp)
        match _type_kind(tp):
            case _TypeKind.UNION:
                return any(
                    _is_collection_patch_path(_resolve_type(v), parts[idx:], union_tag) for v in _union_args_no_none(tp)
                )
            case _TypeKind.LIST | _TypeKind.SET | _TypeKind.FROZENSET | _TypeKind.TUPLE | _TypeKind.DICT:
                return True
            case _TypeKind.NAMEDTUPLE | _TypeKind.CALLABLE:
                return False
        if part in _locals_keys_nested(tp, union_tag):
            return True  # a nested namespace is a dict[str, Any]
        tp = _advance_field_type(tp, part)
        if tp is None:
            return False
    return False


def _registered_when_typed(target: Any, parts: list[str], union_tag: str) -> bool:
    """Return True if the adapters register this path's flag only when argv types it.

    A collection patch (:func:`_is_collection_patch_path`), or a union tag the walk
    reaches by its fallback (:func:`_names_tag_by_fallback`) -- whatever the parent, as
    vanilla's tag rule answers whatever the parent.  The static walk lists neither, so
    the argv scan registers them, and the loop that writes the adapters' CLI channel
    writes them as it writes any flag, in the order argv spells it.

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity
    """
    return _is_collection_patch_path(target, parts, union_tag) or _names_tag_by_fallback(target, parts, union_tag)


def _path_unknown(target: Any, parts: list[str], union_tag: str) -> bool:
    """Return True when *parts* names no node a flag can write: vanilla refuses it as unknown.

    A path the walk resolves is a member; a path below a dict-typed node is a key the dict
    takes, whatever it spells.  The delete handler, the unknown-field handler and the
    adapters' skip of the host's own flags all ask this one question.
    """
    return _resolve_field_type(target, parts, union_tag) is None and not _is_dict_at_path(target, parts, union_tag)


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


def _member_names(pt: Any) -> list[str]:
    """Return the exact spellings of the named members of container type ``pt``.

    A struct's members (:func:`~confarg._types._struct_member_names`, subclass-only names
    included), a namedtuple's fields, and either across a union's variants: the names
    :func:`_segment_names_real_field` answers by declaration. A position counts nothing
    here -- a namedtuple index, a sequence index, a dict key -- and neither does a
    callable's sub-key, for none of those is a declared name.
    """
    pt = _resolve_type(pt)
    if _is_union(pt):
        return list(dict.fromkeys(n for v in _union_args_no_none(pt) for n in _member_names(v)))
    if _is_namedtuple(pt):
        return list(_namedtuple_fields(pt))
    if _is_struct(pt):
        return _struct_member_names(pt)
    return []


def _segment_names_real_field(pt: Any, seg: str, union_tag: str) -> bool:
    """Return True if ``seg`` names a real member of container type ``pt``.

    Decides "field or reserved word?" for force casts and the locals namespace: a real
    field of that name always wins.  Structs, namedtuples, and (recursively) union
    variants are checked for a matching field; for dicts every segment is a real key;
    lists, sets, tuples, callables, and scalars have no named members (False).

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    if seg == union_tag:
        return True
    pt = _resolve_type(pt)
    if _is_union(pt):
        return any(_segment_names_real_field(_resolve_type(v), seg, union_tag) for v in _union_args_no_none(pt))
    if _is_struct(pt):
        return _struct_member_type(pt, seg) is not None
    if _is_namedtuple(pt):
        return seg in _namedtuple_fields(pt)
    # dicts accept any key (real member); lists/sets/tuples/callables/scalars do not.
    return bool(_is_dict(pt))


def _locals_keys(target: Any, union_tag: str) -> tuple[str, ...]:
    """Return the names that address the local-variables namespace for *target*.

    Each candidate from :data:`~confarg._defaults.LOCALS_KEYS` survives unless
    :func:`_segment_names_real_field` says it names a real member of *target*. An
    empty result means the target has no namespace (it owns both names, or is a
    dict). A scalar (``__root__``) root keeps both. Must depend on *target* and
    *union_tag* only.

    Dev Notes:
        docs-dev/architecture/locals.md#derived-name
    """
    return tuple(key for key in _defaults.LOCALS_KEYS if not _segment_names_real_field(target, key, union_tag))


def _locals_keys_nested(tp: Any, union_tag: str) -> tuple[str, ...]:
    """Names addressing a local-variables namespace at a node *inside* the target.

    Only struct-like nodes (structs, namedtuples, unions of them) can hold one. Use
    :func:`_locals_keys` for the root, where a scalar root also keeps the namespace.
    """
    tp = _resolve_type(tp)
    if _is_union(tp):
        found = (k for v in _union_args_no_none(tp) for k in _locals_keys_nested(v, union_tag))
        return tuple(dict.fromkeys(found))
    if not (_is_struct(tp) or _is_namedtuple(tp)):
        return ()
    return _locals_keys(tp, union_tag)


def _locals_keys_at(target: Any, path: list[str], union_tag: str) -> tuple[str, ...]:
    """Names addressing a namespace at *path* within *target*, the root included.

    The one question every consumer (stripping, the declaration scan, the CLI type
    walk, the env parser) asks at each node.

    Dev Notes:
        docs-dev/architecture/locals.md#per-node-namespaces
    """
    if not path:
        return _locals_keys(target, union_tag)
    tp = _resolve_field_type(target, path, union_tag)
    return () if tp is None else _locals_keys_nested(tp, union_tag)


def _locals_segment_index(target: Any, parts: list[str], union_tag: str) -> int | None:
    """Index of the segment at which *parts* enters a namespace, or None."""
    for i in range(len(parts)):
        if parts[i] in _locals_keys_at(target, parts[:i], union_tag):
            return i
    return None


def detect_force_cast(path: list[str], target: Any, union_tag: str) -> tuple[list[str], str | None]:
    """Decide whether ``path``'s trailing segment is a force-cast suffix.

    Returns ``(path_without_cast, cast_name)`` when the last segment is one of
    :data:`~confarg._cast.FORCE_CAST_NAMES` *and* it does not name a real field/key of
    the parent (real field wins); otherwise ``(path, None)``.  A root-level cast (no
    parent to attach to) is a cast only for ``--json`` (whole-config injection, empty
    returned path); root-level scalar casts have no struct to attach to and are ignored.
    """
    if not path or path[-1] not in FORCE_CAST_NAMES:
        return path, None
    parent = path[:-1]
    if not parent:
        # Root-level cast: only `--json` is meaningful (inject the whole config as a
        # JSON object); scalar casts have no struct to attach to. A real root field
        # named `json` still wins, mirroring the nested rule below.
        if path[-1] == JSON_CAST_NAME and not _segment_names_real_field(target, path[-1], union_tag):
            return [], path[-1]
        return path, None
    parent_type = _resolve_field_type(target, parent, union_tag)
    if parent_type is None or _segment_names_real_field(parent_type, path[-1], union_tag):
        return path, None
    return parent, path[-1]


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


class _EqValue(str):
    """The value half of a ``--key=value`` token: a value whatever it looks like.

    Shape alone cannot tell ``--x`` the value from ``--x`` the flag, so the one token
    whose position already proved it is a value carries that proof forward.
    :func:`_looks_like_flag` is the only reader; every consumption site rewraps the
    token (``_StrToken``, ``json.loads``, ``Path``), so the marker never reaches a
    merged dict.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """

    __slots__ = ()


def _looks_like_flag(token: str) -> bool:
    """Check whether a token looks like a CLI flag (--word).

    A flag must start with ``--`` followed by a letter or underscore. Bare
    ``--`` and tokens like ``--:`` or ``--3`` are not flags.  A token that came from
    the value half of ``--key=value`` is never a flag, however it is spelled.

    Args:
        token: The CLI token to check.

    Returns:
        True if the token looks like a CLI flag.
    """
    if isinstance(token, _EqValue):
        return False
    return token.startswith("--") and len(token) > 2 and (token[2].isalpha() or token[2] == "_")  # noqa: PLR2004  # length of the "--" prefix


def _require_value(args: Sequence[str], i: int, token: str, usage: str = "<value>") -> None:
    """Raise unless *args* holds a value for *token* at *i*.

    The one guard behind "a value-taking flag always needs its value": argv running out
    and the next token being another flag are the same failure, so every value-consuming
    branch asks it here instead of spelling the test again -- including the fixed-arity
    branch, which asks it once per positional token
    (:func:`_consume_fixed_tuple_args`).  *usage* is passed through to
    :meth:`ConfargError.missing_value`.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    if i >= len(args) or _looks_like_flag(args[i]):
        raise ConfargError.missing_value(token, usage)


def _check_reserved_key_conflict(target: Any, name: str, detail: str) -> None:
    """Raise ConfargError if the reserved name *name* is also a top-level field of *target*.

    Used for every reserved top-level name. *detail* supplies the name-specific
    explanation and remedy. A falsy *name* means the feature is disabled.
    """
    if not name:
        return

    def _check_struct(tp: Any) -> None:
        if name in _struct_fields(tp):
            tp_name = getattr(tp, "__name__", repr(tp))
            msg = f"{name!r} is a reserved name but {tp_name} has a field named {name!r}. {detail}"
            raise ConfargError(msg)

    tp = _resolve_type(target)
    if _is_struct(tp):
        _check_struct(tp)
    elif _is_union(tp):
        for variant in _union_args_no_none(tp):
            v = _resolve_type(variant)
            if _is_struct(v):
                _check_struct(v)


def _check_config_flag_conflict(target: Any, config_flag: str, cli_prefix: str) -> None:
    """Raise ConfargError if config_flag matches a top-level field name of target.

    When config_flag shadows a field name the user can never set that field via
    --{config_flag}, because the parser intercepts it as a file-path argument.
    """
    flag_display = f"--{cli_prefix}.{config_flag}" if cli_prefix else f"--{config_flag}"
    _check_reserved_key_conflict(
        target,
        config_flag,
        f"It names the config-file flag ({flag_display}), so the field cannot be set via CLI:"
        f" the flag is intercepted before field lookup."
        f" Pass a different config_flag to merge()/load(), e.g. config_flag='conf'.",
    )


# ---------------------------------------------------------------------------
# Helpers for the main parse loop
# ---------------------------------------------------------------------------


def _normalize_eq_args(args: Sequence[str]) -> list[str]:
    """Split --key=value tokens into --key value pairs.

    The value half comes back as an :class:`_EqValue`, so a value that itself looks
    like a flag (``--key=--value``) survives every later flag-check, and re-running
    this over an already-normalized argv -- which the adapters do -- splits it no
    further.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    normalized: list[str] = []
    for tok in args:
        if not isinstance(tok, _EqValue) and tok.startswith("--") and "=" in tok:
            flag, _, val = tok.partition("=")
            normalized.append(flag)
            normalized.append(_EqValue(val))
        else:
            normalized.append(tok)
    return normalized


def _in_cli_prefix(raw_key: str, cli_prefix: str) -> bool:
    """Return True when the flag *raw_key* spells lives in the *cli_prefix* namespace."""
    return not cli_prefix or raw_key == cli_prefix or raw_key.startswith(f"{cli_prefix}.")


def _strip_cli_prefix(raw_key: str, cli_prefix: str, token: str) -> str:
    """Return raw_key with cli_prefix stripped, or raise UnknownArgumentError."""
    if not cli_prefix:
        return raw_key
    if not _in_cli_prefix(raw_key, cli_prefix):
        raise UnknownArgumentError.wrong_prefix(token, cli_prefix)
    return "" if raw_key == cli_prefix else raw_key.removeprefix(f"{cli_prefix}.")


@functools.cache
def _locals_walk_root(locals_keys: tuple[str, ...]) -> Any:
    """Return a dataclass with one ``dict[str, Any]`` field per local-variables key.

    Grafted onto the walk target by :func:`_walk_target` so ``--<key>.<name>`` paths
    resolve like a real dict field. Validation happens in the pipeline, not here.

    Dev Notes:
        docs-dev/architecture/locals.md#walk-target-graft
    """
    name = "_LocalsRoot_" + "_".join(locals_keys)
    return dataclasses.make_dataclass(name, [(key, dict[str, Any]) for key in locals_keys])


def _walk_target(target: Any, locals_keys: tuple[str, ...]) -> Any:
    """Return the target to resolve dotted paths against, with the locals namespace grafted on.

    Use the result *only* for path resolution; classify the root (scalar vs struct)
    and check config-flag conflicts against the real ``target``. *locals_keys* must
    come from :func:`_locals_keys`: grafting a name that is also a real field silently
    routes ``--<name>.x`` away from that field. Nested namespaces are handled by
    :func:`_resolve_field_type` itself.

    Dev Notes:
        docs-dev/architecture/locals.md#walk-target-graft
    """
    if not locals_keys:
        return target
    return target | _locals_walk_root(locals_keys)


def _addresses_key(key: str, reserved: str) -> bool:
    """Return True when a dotted flag/env path addresses the reserved name *reserved*.

    That is, the bare name or any dotted path beneath it, with or without a trailing merge
    suffix: ``--config``, ``--config.db``, ``--config.dbs+`` and a bare ``--config+`` all
    address the config flag. The last of them is a mistake, but it is a mistake *about this
    flag*, so it is intercepted here and reported by the one error that explains it rather
    than looking like an unknown flag. A falsy *reserved* never matches.
    """
    if not reserved:
        return False
    key = key.removesuffix(LIST_APPEND_KEY)
    return key == reserved or key.startswith(reserved + ".")


def _config_subpath(key: str, config_flag: str) -> str:
    """Return the mount subpath a ``--<config_flag>…`` flag key addresses.

    ``config`` and ``config+`` address the root (``""`` and ``"+"``), ``config.db`` addresses
    ``db``, ``config.dbs+`` addresses ``dbs+``. A trailing merge suffix is carried through
    rather than stripped, because what appending means is the pipeline's call, not the scan's.
    Both vanilla's scan and the adapters' re-scan read it from here, so they cannot
    disagree by accident.
    """
    if key.startswith(config_flag + "."):
        return key[len(config_flag) + 1 :]
    return key[len(config_flag) :]


def _mount_owner(tp: Any) -> tuple[str, Sequence[str] | None]:
    """Return the type name and field names of the node a mount check fails in.

    A union gathers the field names of its struct-like variants, so a subpath that misses
    every variant at once is told what any of them would have accepted; ``None`` means the
    node holds no named fields at all (a scalar, a collection).
    """
    tp = _resolve_type(tp)
    if _is_struct(tp):
        return tp.__name__, tuple(_struct_fields(tp))
    if _is_namedtuple(tp):
        return tp.__name__, tuple(_namedtuple_fields(tp))
    if _is_union(tp):
        names = sorted({n for v in _union_args_no_none(tp) for n in (_mount_owner(v)[1] or ())})
        return str(tp), tuple(names) or None
    return getattr(tp, "__name__", str(tp)), None


def _check_mount_subpath(target: Any, subpath: str, union_tag: str, spelling: str) -> None:
    """Raise when a config-flag mount subpath names no node of *target*.

    The check the flag's interception runs once the type walk is available: the flag is
    intercepted *before* field lookup, so a misspelled subpath would otherwise mount a whole
    file at a key nobody declared and surface much later as an unknown-field error from
    ``build()``. A trailing merge suffix is stripped first; the empty subpath is the root and
    always valid. A path is accepted at whatever depth it resolves — dict keys and sequence
    indices included — because whether the node it names can hold the fragment is the mount's
    call, not the scan's.

    *spelling* is the flag as its own channel writes it (``--config.dbb``,
    ``CONFARG_CONFIG__DBB``), passed in because the walk that decides cannot know it. The
    environment passes an already-resolved subpath, because its match is case-insensitive
    and this walk is exact.

    Raises:
        ConfargError: When the subpath names no field of the node it descends to.

    Dev Notes:
        docs-dev/architecture/cli-parsing/type-guided-parsing.md#type-guided-parsing
    """
    path = subpath.removesuffix(LIST_APPEND_KEY)
    if not path:
        return
    walk_target = _walk_target(target, _locals_keys(target, union_tag))
    parts = path.split(".")
    for j in range(1, len(parts) + 1):
        if _resolve_field_type(walk_target, parts[:j], union_tag) is not None:
            continue
        owner = _resolve_field_type(target, parts[: j - 1], union_tag)
        name, valid = _mount_owner(owner)
        raise ConfargError.no_such_mount_point(spelling, name, valid)


def _missing_config_path_msg(config_flag: str) -> str:
    """Build the error a --config[.subpath] occurrence with no path token after it raises."""
    return f"Missing file path after --{config_flag}. Usage: --{config_flag} /path/to/config.yaml"


def _consume_config_paths(args: list[str], i: int, key: str, config_flag: str) -> tuple[int, list[tuple[str, str]]]:
    """Consume config-location tokens for a --config[.subpath] flag.

    Returns (new_i, [(subpath, mount value)]); the value is the raw token -- a local path, a
    URL, or a JSON fragment -- read as an ``__include__`` value by the pipeline
    (docs-dev/architecture/config-files/mounting.md#mounting).
    """
    subpath = _config_subpath(key, config_flag)
    i += 1
    if i >= len(args) or _looks_like_flag(args[i]):
        raise ConfargError(_missing_config_path_msg(config_flag))
    pairs: list[tuple[str, str]] = []
    while i < len(args) and not _looks_like_flag(args[i]):
        pairs.append((subpath, args[i]))
        i += 1
    return i, pairs


def _parse_flag_mode(
    key: str,
) -> tuple[list[str], bool, bool, int, bool]:
    """Decode append/delete mode flags from a flag key.

    Returns ``(path, append_mode, delete_mode, delete_idx, is_list_delete)``.  Force-cast
    suffixes are *not* decoded here; see :func:`detect_force_cast`.
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
        with contextlib.suppress(ValueError):
            delete_idx = int(raw_last)
            is_list_delete = True

    return path, append_mode, delete_mode, delete_idx, is_list_delete


@dataclass
class _ParseCtx:
    """Shared parse-loop state threaded through token handlers."""

    argv: Sequence[str]
    target: Any
    union_tag: str
    data: dict[str, Any] = field(default_factory=dict)
    multi_tokens: dict[tuple[str, ...], list[str]] = field(default_factory=dict)
    """Tokens every plain multi-token occurrence contributed, keyed by field path.

    Repeating such a flag is a second spelling of listing its tokens in one go, so the
    accumulated list — not the newest occurrence alone — is what gets shaped into the
    stored value.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """


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
        if _path_unknown(ctx.target, path, ctx.union_tag):
            raise UnknownArgumentError.not_indexable(token, parent_path)
        node: Any = ctx.data
        for _p in parent_path:
            node = node[_p] if isinstance(node, dict) and _p in node else {}
        del_key = LIST_POST_APPEND_DELETE_KEY if isinstance(node, dict) and LIST_APPEND_KEY in node else LIST_DELETE_KEY
        _accumulate_list_delete(ctx.data, parent_path, delete_idx, token, delete_key=del_key)
    else:
        if _path_unknown(ctx.target, path, ctx.union_tag):
            raise UnknownArgumentError.no_such_field(token, path)
        # A whole-field delete ends the value at this path, so a later multi-token occurrence
        # starts a new list rather than extending the one the delete just discarded. An index
        # delete is a patch *within* the list and leaves the accumulation alone.
        ctx.multi_tokens.pop(tuple(path), None)
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


def _consume_fixed_tuple_args(  # noqa: PLR0913  # token only names the flag in the error
    args: Sequence[str],
    i: int,
    token: str,
    tt: list[Any],
    path: list[str],
    data: dict[str, Any],
) -> int:
    """Consume exactly len(tt) arguments for a fixed-length tuple field.

    Every one of them is required: a fixed arity is not a shape a bare flag is reserved
    for, so argv running short -- or reaching the next flag -- is a missing value and not
    a shorter tuple (BUG-43).

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    items: list[Any] = []
    for et in tt:
        _require_value(args, i, token)
        items.append(_try_coerce(et, _StrToken(args[i])))
        i += 1
    _set_nested(data, path, items)
    return i


def _union_seq_value(ft: Any, tokens: list[str], token: str) -> Any:
    """Shape a union-with-sequence-variant field's accumulated tokens into its value.

    A single token is stored as a bare scalar when the union also has a scalar
    variant (so ``--input foo`` stays ``'foo'``); it is marked with
    ``_UnionSeqToken`` so that, if every scalar variant rejects it, ``construct``
    can still fall back to filling the sequence variant as a one-element list
    (so ``--input hello`` for ``bool | list[str]`` becomes ``['hello']``).
    Otherwise the tokens form a list and tuple/list/set disambiguation is
    deferred to ``construct``. No tokens builds the empty list when the union has
    a varlen variant (e.g. ``int | list[int]`` → ``[]``); otherwise it is a
    missing-value error.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#unions-with-sequence-variants
    """
    parsed = _lone_json_array(tokens)
    if parsed is not None:
        return parsed
    if not tokens:
        if _union_has_varlen_variant(ft):
            return []
        raise ConfargError.missing_value(token)
    if len(tokens) == 1 and _union_has_scalar_variant(ft):
        return _UnionSeqToken(_StrToken(tokens[0]))
    return [_StrToken(t) for t in tokens]


def _handle_scalar_root(args: list[str], i: int, token: str, target_r: Any, data: dict[str, Any]) -> int:
    """Consume the single value for a non-struct scalar target. Returns new arg index."""
    i += 1
    _require_value(args, i, token)
    data[_defaults.ROOT_KEY] = _try_coerce(target_r, _StrToken(args[i]))
    return i + 1


def _handle_root_cast(  # noqa: PLR0913  # each arg carries distinct root-placement context
    args: list[str],
    i: int,
    token: str,
    *,
    is_struct: bool,
    cast_name: str,
    data: dict[str, Any],
    root_json: list[dict[str, Any]],
) -> int:
    """Consume the value for a root-level ``--json`` cast. Returns new arg index.

    For a struct/union root the decoded object must be a JSON object; it is collected
    into ``root_json`` and folded in as a base (so per-field CLI flags win) once the
    whole argv is parsed by :func:`~confarg._cast.fold_root_json`.  For a scalar root the
    decoded value is stored under ``__root__``, written in argv order like the bare
    ``--<cli_prefix>`` flag, so of the two the last typed wins.  Invalid JSON raises via
    :func:`resolve_forced_value`.
    """
    i += 1
    _require_value(args, i, token, "'<json>'")
    value = resolve_forced_value(cast_name, args[i], flag=token)
    if is_struct:
        if not isinstance(value, dict):
            raise ConfargError.root_cast_not_object(token, value)
        root_json.append(value)
    else:
        data[_defaults.ROOT_KEY] = value
    return i + 1


def _handle_force_cast(  # noqa: PLR0913  # cast_name is a necessary discriminator, not incidental
    args: list[str],
    i: int,
    token: str,
    data: dict[str, Any],
    path: list[str],
    cast_name: str,
) -> int:
    """Consume the value for a ``.<cast>`` flag and store the forced value. Returns new arg index.

    Scalar casts store a ``_Pinned`` token; ``.json`` stores the decoded structure and
    raises ``ConfargError`` on invalid JSON (via :func:`resolve_forced_value`).
    """
    _require_value(args, i, token)
    _set_nested(data, path, resolve_forced_value(cast_name, args[i], flag=token))
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
        raise UnknownArgumentError.no_such_field(token, path)
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
    raise UnknownArgumentError.no_such_field(token, path)


def _try_parse_json_list(arg: str) -> list[Any] | None:
    """Parse arg as a JSON array and return it, or None if not valid JSON or not a list."""
    try:
        parsed = json.loads(arg)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _lone_json_array(tokens: list[str]) -> list[Any] | None:
    """Return the decoded array when *tokens* is one inline JSON array, else None.

    The inline array is a **whole-value** spelling, so it is only that when it stands
    alone: a second token — from the same occurrence or a later one — makes every token
    an ordinary item instead. Elements are returned raw (plain values, not
    ``_StrToken``), which is what exempts them from the stealing rule and makes ``null``
    expressible.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    if len(tokens) != 1 or not tokens[0].startswith("["):
        return None
    return _try_parse_json_list(tokens[0])


def _varlen_value(ft: Any, tokens: list[str]) -> Any:
    """Shape a varlen collection field's accumulated tokens into its stored value.

    One inline JSON array standing alone is decoded as the whole value; otherwise every
    token becomes an element, coerced eagerly to the element type so the merged dict
    carries the same types whichever channel supplied them.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    parsed = _lone_json_array(tokens)
    if parsed is not None:
        return parsed
    et = _elem_type(ft)
    return [_try_coerce(et, _StrToken(t)) for t in tokens]


def _consume_multi_tokens(ctx: _ParseCtx, i: int, path: list[str]) -> tuple[list[str], int]:
    """Consume this occurrence's tokens and return every occurrence's, plus the new index.

    Values run until the next flag. A repeated multi-token flag is a second spelling of
    one carrying every token, so the occurrences are joined in argv order rather than the
    newest replacing the rest.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    args = ctx.argv
    tokens = ctx.multi_tokens.setdefault(tuple(path), [])
    while i < len(args) and not _looks_like_flag(args[i]):
        tokens.append(args[i])
        i += 1
    return tokens, i


def _consume_collection_or_scalar(
    ctx: _ParseCtx,
    i: int,
    token: str,
    ft: Any,
    path: list[str],
) -> int:
    """Consume collection (array/tuple/varlen) or scalar value; return new arg index."""
    args = ctx.argv
    # Fixed-length sequence: one whole-value JSON array in place of its positional tokens.
    # The multi-token families below decide the same thing on their accumulated tokens.
    tt = _fixed_seq_types(ft)
    if (
        tt is not None
        and i < len(args)
        and not _looks_like_flag(args[i])
        and (parsed := _lone_json_array([args[i]])) is not None
    ):
        _set_nested(ctx.data, path, parsed)
        return i + 1

    # Variable-length collection → consume until the next flag, extending a prior occurrence
    if _is_varlen_collection(ft):
        tokens, i = _consume_multi_tokens(ctx, i, path)
        _set_nested(ctx.data, path, _varlen_value(ft, tokens))
        return i

    # Fixed-length sequence (tuple[X, Y] or a namedtuple) → consume exact count
    if tt is not None:
        return _consume_fixed_tuple_args(args, i, token, tt, path, ctx.data)

    # Union with a sequence variant → consume greedily (disambiguation deferred to construct)
    if _union_has_seq_variant(ft):
        tokens, i = _consume_multi_tokens(ctx, i, path)
        _set_nested(ctx.data, path, _union_seq_value(ft, tokens, token))
        return i

    # Default: consume one scalar value
    _require_value(args, i, token)
    _set_nested(ctx.data, path, _try_coerce(ft, _StrToken(args[i])))
    return i + 1


def _accepts_object_value(ft: Any) -> bool:
    """Return whether a field of type *ft* takes a whole ``{...}`` JSON token as its value.

    The one test behind every whole-value flag, and behind the env channel's ``{``-led
    value: it decides what the vanilla parser decodes, which bare ``--<field>`` flags the
    CLI adapters register and decode, and which environment variable holds a blob, so the
    four can never disagree.  Pass the field type as resolved, *without* unwrapping
    ``Optional``: the union arm answers for the optional spellings, so ``dict[str, str]``
    and ``dict[str, str] | None`` take the same token, and so do ``Callable[..., T]``
    and ``Callable[..., T] | None``.

    A *struct* is either spelling of one -- a dataclass or a plain class -- because the
    blob is taken apart into fields, and construction takes both apart the same way.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """

    def accepts(v: Any) -> bool:
        v = _resolve_type(v)
        return _is_struct(v) or _is_namedtuple(v) or _is_dict(v) or _is_callable(v)

    return accepts(ft) or (_is_union(ft) and any(accepts(v) for v in _union_args_no_none(ft)))


def _takes_callable_shorthand(ft: Any) -> bool:
    """Return whether a bare string at a field of type *ft* is a callable spec shorthand.

    Mirrors the union handling of :func:`_accepts_object_value`: the union arm answers for
    the optional spellings, so ``Callable[..., T] | None`` reads a bare string the same way
    ``Callable[..., T]`` does.
    """

    def is_callable_variant(v: Any) -> bool:
        return _is_callable(_resolve_type(v))

    return is_callable_variant(ft) or (_is_union(ft) and any(is_callable_variant(v) for v in _union_args_no_none(ft)))


def _open_callable_shorthand(data: dict[str, Any], path: list[str], target: Any, union_tag: str) -> None:
    """Open a bare-string callable value into its dict form before *path* descends into it.

    ``--fn pkg.func`` is the shorthand for ``--fn.fn pkg.func``, so a later
    ``--fn.bind.<param>`` must refine the target the shorthand named, not erase it.  This is
    the one place that decides it, for every channel: the CLI parse loop and the env parse
    loop both call it before they store, so ``FN=pkg.func`` plus ``FN__BIND__SEP=-`` reads
    the same as the two flags.

    A segment that names an *opener* is not a refinement but a second spelling of the
    target, so it replaces the shorthand rather than joining it — the rule that already
    makes an opener flag beat the whole-value blob it sits next to.  A field with no such
    shorthand is left alone: its scalar means nothing, and :func:`~confarg._merge._set_nested`
    replaces it.

    Args:
        data: The dict being built, modified in place.
        path: Path segments of the flag or variable about to be stored.
        target: The type paths resolve against (locals-grafted, where that applies).
        union_tag: The field name used as a union discriminator.

    Dev Notes:
        docs-dev/architecture/callables.md#cli
    """
    for n in range(1, len(path)):
        if names_an_opener(path[n]):
            continue
        existing = _peek_nested(data, path[:n])
        if not isinstance(existing, str):
            continue
        ft = _resolve_field_type(target, path[:n], union_tag)
        if ft is not None and _takes_callable_shorthand(_resolve_type(ft)):
            _set_nested(data, path[:n], promote_bare_spec(existing))


def _promote_namedtuple_positional(data: dict[str, Any], path: list[str], target: Any, union_tag: str) -> None:
    """Re-key a namedtuple field's positional list under its field names before *path* descends.

    The sibling of :func:`_open_callable_shorthand`, run at the same point in the loop:
    the arity flag stores a plain list, and ``_set_nested`` would promote it to
    ``{LIST_REPLACE_BASE_KEY: list}`` -- the list-op shape an index patch on a *varlen*
    collection rides on.  A namedtuple's positions are its fields, so the promotion is
    by field name: a sub-flag that follows the arity flag joins the positions it did not
    take, and the merged dict stays one ``build()`` can read, both shapes a namedtuple
    accepts (BUG-66).  Write order decides: only a sub-flag descends, so the promotion
    runs when the arity flag came first, and a later arity flag still replaces the
    whole field.

    Asked of the field as resolved, like every dispatch here: ``Optional[Point]`` is a
    union with a sequence variant, whose own branch stores the ``'*'`` shape, so it is
    no business of this one.

    Args:
        data: The dict being built, modified in place.
        path: Path segments of the flag about to be stored.
        target: The type paths resolve against (locals-grafted, where that applies).
        union_tag: The field name used as a union discriminator.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    for n in range(1, len(path)):
        existing = _peek_nested(data, path[:n])
        if not isinstance(existing, list):
            continue
        ft = _resolve_field_type(target, path[:n], union_tag)
        if ft is None:
            continue
        core = _resolve_type(ft)
        if not _is_namedtuple(core):
            continue
        _set_nested(data, path[:n], dict(zip(_namedtuple_fields(core), existing, strict=False)))


def _consume_typed_arg(
    ctx: _ParseCtx,
    i: int,
    token: str,
    ft: Any,
    path: list[str],
) -> int:
    """Consume the value(s) for a resolved, non-append field type and return the new arg index.

    A whole-value flag needs its value: the bare ``--<struct>`` form falls through to the
    missing-value error every other value-taking flag raises.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    args = ctx.argv
    # JSON object → dataclass / dict / callable / union-with-dc
    if i < len(args) and not _looks_like_flag(args[i]) and args[i].startswith("{") and _accepts_object_value(ft):
        _set_nested(ctx.data, path, _parse_json_arg(args[i], token))
        return i + 1

    return _consume_collection_or_scalar(ctx, i, token, ft, path)


def _collect_config_file_pairs(
    argv: Sequence[str],
    config_flag: str,
    target: Any,
    union_tag: str,
) -> list[tuple[str, str]]:
    """Return (subpath, mount value) pairs for ``--config[.subpath]`` flags in command-line order.

    Cyclopts' pre-parse refusal: cyclopts asserts on a ``nargs="*"`` flag with zero
    tokens before confarg's loop ever reads argv, so a bare ``--config[.subpath]`` is
    refused here first, raising exactly what vanilla's parse raises, off the same
    message builders — including the check that a subpath names a node of *target*.

    Takes argv with any ``cli_prefix`` already removed
    (:func:`~confarg.cli._prefix.strip_argv_prefix`), so this scan never has to know
    about it.

    Args:
        argv: The CLI argument sequence to scan, free of any ``cli_prefix``.
        config_flag: The flag name used to specify config files (e.g. ``"config"``).
        target: The target type the subpaths are checked against.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        A list of ``(subpath, mount value)`` pairs in the order they appear in argv.

    Raises:
        ConfargError: A ``--config[.subpath]`` occurrence with no path token after it,
            or a subpath that names no node of *target*.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """
    normalized = _normalize_eq_args(list(argv))
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(normalized):
        token = normalized[i]
        if not _looks_like_flag(token):
            i += 1
            continue
        raw_key = token[2:]
        if _addresses_key(raw_key, config_flag):
            subpath = _config_subpath(raw_key, config_flag)
            _check_mount_subpath(target, subpath, union_tag, token)
            i += 1
            if i >= len(normalized) or _looks_like_flag(normalized[i]):
                raise ConfargError(_missing_config_path_msg(config_flag))
            while i < len(normalized) and not _looks_like_flag(normalized[i]):
                pairs.append((subpath, normalized[i]))
                i += 1
        else:
            i += 1
    return pairs


def _skip_flag_values(argv: Sequence[str], i: int) -> int:
    """Advance past a flag token at *i* and any following non-flag value tokens."""
    i += 1
    while i < len(argv) and not _looks_like_flag(argv[i]):
        i += 1
    return i


def _parse_cli(  # noqa: C901, PLR0912, PLR0913, PLR0915  # single argv parse loop, vanilla's and the adapters'
    argv: Sequence[str],
    target: Any,
    cli_prefix: str,
    config_flag: str,
    union_tag: str,
    *,
    host_parsed: bool = False,
    host_binds_run: Callable[[Any], bool] | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Parse CLI arguments into a nested dict and a list of config file paths.

    Args:
        argv: The CLI argument sequence to parse.
        target: The target type, used for type-aware parsing decisions.
        cli_prefix: Required prefix for CLI flags (empty string for no prefix).
        config_flag: The flag name used to specify config files.
        union_tag: The field name used as a discriminator tag in unions.
        host_parsed: The argv is one a host framework already parsed for an adapter,
            beside parameters of its own.  A token the host owns -- a positional or
            subcommand token no flag consumes, a flag outside *cli_prefix*, or, with no
            prefix, a flag whose first segment names no member of *target* -- is
            skipped with its values instead of refused.  Everything in confarg's
            namespace is parsed exactly as vanilla parses it, so the adapters' CLI
            channel is this loop's own output.
        host_binds_run: Asked of the type a flag consumed for when the token after
            its run is a value: True when the host bound that token to the flag (a
            framework registering the flag greedily), so it is the stray vanilla
            refuses rather than a positional of the host's.  ``None`` for vanilla,
            whose own loop refuses every stray at the top.

    Returns:
        A tuple of (data_dict, config_files) where data_dict is the parsed
        argument data and config_files is a list of (subpath, mount value) pairs.

    Raises:
        UnknownArgumentError: If an unrecognized argument is encountered.
        ConfargError: If a config flag is missing its path argument or conflicts with a field name.
    """
    _check_config_flag_conflict(target, config_flag, cli_prefix)
    argv = _normalize_eq_args(argv)
    # Before any path resolves: a subclass named by the tag is invisible to
    # _struct_member_type until its module has run.
    import_tagged_classes(argv, target, union_tag=union_tag, config_flag=config_flag)

    # Paths resolve against the locals-grafted target; root classification keeps `target`.
    walk_target = _walk_target(target, _locals_keys(target, union_tag))
    ctx = _ParseCtx(argv=argv, target=walk_target, union_tag=union_tag)
    config_files: list[tuple[str, str]] = []
    root_json: list[dict[str, Any]] = []  # objects from root `--json`, folded in below fields
    target_r = _resolve_type(target)
    is_struct = _is_struct_like(target_r)
    i = 0

    while i < len(argv):
        token = argv[i]
        if not _looks_like_flag(token):
            if host_parsed:
                i += 1  # a positional or subcommand token of the host's own
                continue
            raise UnknownArgumentError.unexpected_positional(token)

        if host_parsed and not _in_cli_prefix(token[2:], cli_prefix):
            i = _skip_flag_values(argv, i)  # a flag the host registered outside the namespace
            continue
        key = _strip_cli_prefix(token[2:], cli_prefix, token)

        if _addresses_key(key, config_flag):
            _check_mount_subpath(target, _config_subpath(key, config_flag), union_tag, token)
            i, new_cfgs = _consume_config_paths(argv, i, key, config_flag)
            config_files.extend(new_cfgs)
            continue

        path, append_mode, delete_mode, delete_idx, is_list_delete = _parse_flag_mode(key)

        force_cast: str | None = None
        if not append_mode and not delete_mode:
            path, force_cast = detect_force_cast(path, walk_target, union_tag)

        if host_parsed and not cli_prefix and path and _path_unknown(walk_target, path[:1], union_tag):
            i = _skip_flag_values(argv, i)  # a flag the host registered beside the confarg ones
            continue

        # A bare callable shorthand already stored at a prefix of this path is a spec, not
        # a stale scalar: open it so this flag refines it
        # (docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption).
        _open_callable_shorthand(ctx.data, path, walk_target, union_tag)
        _promote_namedtuple_positional(ctx.data, path, walk_target, union_tag)

        if delete_mode:
            _handle_delete_token(ctx, token, path, is_list_delete=is_list_delete, delete_idx=delete_idx)
            i += 1
            continue

        if force_cast is not None and not path:  # root-level `--json`: inject the whole config
            i = _handle_root_cast(
                argv,
                i,
                token,
                is_struct=is_struct,
                cast_name=force_cast,
                data=ctx.data,
                root_json=root_json,
            )
            continue

        if not is_struct and not path:
            i = _handle_scalar_root(argv, i, token, target_r, ctx.data)
            continue

        if is_struct and not path:
            # The bare --<prefix> flag is a scalar root's only CLI spelling; on a
            # struct-like root its value would be written at the empty path, a no-op.
            raise UnknownArgumentError.bare_prefix_on_struct_root(token, cli_prefix)

        ft = _resolve_field_type(walk_target, path, union_tag)
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
        if host_binds_run is not None and i < len(argv) and not _looks_like_flag(argv[i]) and host_binds_run(ft):
            # The host bound the token after the run to this flag, so it is no positional of
            # the host's: it is the stray vanilla refuses.
            raise UnknownArgumentError.unexpected_positional(argv[i])

    return fold_root_json(ctx.data, root_json, union_tag), config_files

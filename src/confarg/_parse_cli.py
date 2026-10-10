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
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator, Sequence

from confarg import _defaults
from confarg._callable import names_a_call, names_a_target_opener, names_an_opener, promote_bare_spec
from confarg._cast import (
    FORCE_CAST_NAMES,
    JSON_CAST_NAME,
    SCALAR_CAST_TYPES,
    fold_root_json,
    holds_the_cast,
    resolve_forced_value,
)
from confarg._merge import (
    APPEND_SUFFIX,
    DELETE_SUFFIX,
    DICT_DELETE,
    LIST_APPEND_KEY,
    LIST_DELETE_KEY,
    LIST_POST_APPEND_DELETE_KEY,
    _accumulate_list_delete,
    _open_for_ops,
    _peek_nested,
    _set_nested,
)
from confarg._tags import _partial_config_from_argv, import_tagged_classes
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
    _union_args,
    _union_args_no_none,
    _union_has_scalar_variant,
    _union_has_seq_variant,
    _union_has_varlen_variant,
    _UnionSeqToken,
)
from confarg.dictexpr._expressions import _list_index
from confarg.exceptions import ConfargError, UnknownArgumentError
from confarg.typedload._coerce import _try_coerce, _type_kind, _TypeKind
from confarg.typedload._construct import _selects_none, _takes_typed_call


def _step_tuple_type(tp: Any, part: str) -> Any | None:
    """Advance one step into a tuple type by numeric index.

    A variadic tuple takes an index as a list does, only as ``str()`` writes one.
    """
    et = _tuple_types(tp)
    if et is None:
        return _elem_type(tp) if _list_index(part) is not None else None
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
    tag may still open it. An open-ended sequence is entered only by an index as ``str()``
    writes one (:func:`~confarg.dictexpr._expressions._list_index`): any other key below it
    would reach the merge as one of its own list-patch keys (BUG-170).

    Dev Notes:
        docs-dev/architecture/cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index
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
            return _elem_type(tp) if _list_index(part) is not None else None
        case _TypeKind.TUPLE:
            return _step_tuple_type(tp, part)
        case _TypeKind.DICT:
            _, vt = _dict_kv(tp)
            return vt
        case _TypeKind.CALLABLE:
            # The openers ("bind", "class", "call", "classfn") and flat kwargs alike
            return str
        case _TypeKind.ANY | _TypeKind.UNION | _TypeKind.LEAF:
            return None


class _Stone(NamedTuple):
    """Where a branch of :func:`_walk_path` stands to step along one path segment."""

    #: The type the walk reached here, a union unexpanded: what a walk of the path so far answers.
    reached: Any
    #: The resolved, non-union type this branch takes ``reached`` as.
    node: Any


class _Branch(NamedTuple):
    """One branch of :func:`_walk_path`: the variant it took at each union it met."""

    #: One per segment the branch stood before: ``stones[k]`` is where it met ``parts[k]``.
    stones: tuple[_Stone, ...]
    #: The type reached at the end of the path, a union unexpanded; ``None`` when the branch
    #: refuses a segment, its last stone then the one it could not step from.
    end: Any | None


#: The kinds whose patch is a list patch: the merge reads every key below one as an index or as
#: one of its own list-patch keys, a namedtuple's field names aside.
_SEQUENCE_KINDS = frozenset(
    {_TypeKind.LIST, _TypeKind.SET, _TypeKind.FROZENSET, _TypeKind.TUPLE, _TypeKind.NAMEDTUPLE},
)

#: The kinds a collection patch stands on: the merge reads every key below one as an index,
#: an op or a dict key. A namedtuple is none of them: the static walk lists its own fields
#: and indices (BUG-157).
_COLLECTION_KINDS = frozenset(
    {_TypeKind.LIST, _TypeKind.SET, _TypeKind.FROZENSET, _TypeKind.TUPLE, _TypeKind.DICT},
)


def _refuses_at_a_sequence(branch: _Branch) -> bool:
    """Return True if *branch* refuses its path standing on a sequence, at a segment naming no element of it.

    Dev Notes:
        docs-dev/architecture/cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index
    """
    return branch.end is None and _type_kind(branch.stones[-1].node) in _SEQUENCE_KINDS


def _union_branches(tp: Any) -> list[Any]:
    """Return the resolved, non-union types a node of type *tp* is walked as, in variant order.

    *tp* itself when it is no union; otherwise each non-None variant, a variant that is a
    union in turn spread into its own.
    """
    tp = _resolve_type(tp)
    if not _is_union(tp):
        return [tp]
    return [node for v in _union_args_no_none(tp) for node in _union_branches(v)]


def _opens_target(stone: _Stone, part: str, depth: int) -> bool:
    """Return True if *part*, met at *stone*, is an opener whose value is a target: a str subtree.

    A ``bind`` or ``call`` key of a callable field, in either form, and a ``call`` key of a
    field that takes a typed call (:func:`~confarg.typedload._construct._takes_typed_call`)
    hold a target: a dotted path (``--f.call pkg.g``) or a callable spec of its own,
    addressable key by key (``--f.call.classfn pkg.C.m``). In escaped mode a plain ``bind``
    is a scalar kwarg (``--f.bind 5``); which it is, construction decides from the opener,
    not here (lenient parse). The root (*depth* 0) holds no typed call: its flags share the
    namespace with a host framework's own.

    Dev Notes:
        docs-dev/architecture/callables.md#cli
    """
    if _is_callable(stone.node):
        return names_a_target_opener(part)
    return depth > 0 and names_a_call(part) and _takes_typed_call(stone.reached, part)


def _walk_path(
    target: Any,
    parts: list[str],
    union_tag: str,
    *,
    tag_fallback: bool = True,
    calls: Collection[tuple[str, ...]] = (),
) -> Iterator[_Branch]:
    """Walk the type tree along *parts*, yielding one branch per way the walk can take it.

    The one type walk. A union met before the path ends is walked once per non-None
    variant, so the walk forks there, and the branches come in variant order; a branch
    that refuses a segment ends there, and a path ending *on* a union-typed node ends on
    that union, unexpanded. Every question about a path is asked of these branches:
    :func:`_field_types` reads their ends, and the predicates over a path --
    :func:`_addresses_callable_key`, :func:`_is_collection_patch_path`,
    :func:`_is_dict_at_path` -- read the stones each stood on.

    A segment names the union tag only when no real member of that exact spelling exists
    at its position; a field named like the tag is that field.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.
        tag_fallback: Whether a segment no member reaches may still name the union tag.
            Off, the walk answers members only, which is how
            :func:`_names_tag_by_fallback` tells the two apart.
        calls: The paths at which the command line opens a typed call
            (:func:`_typed_call_openings`). A segment no member reaches below one of them
            is an argument of the call's target, a ``str`` leaf.

    Dev Notes:
        docs-dev/architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions
    """

    def walk(reached: Any, stones: tuple[_Stone, ...], *, str_subtree: bool) -> Iterator[_Branch]:
        if len(stones) == len(parts):
            yield _Branch(stones, reached)
            return
        part = parts[len(stones)]
        for node in _union_branches(reached):
            here = (*stones, _Stone(reached, node))
            if str_subtree or _opens_target(here[-1], part, len(stones)):
                yield from walk(str, here, str_subtree=True)
            elif part in _locals_keys_nested(node, union_tag):
                yield from walk(dict[str, Any], here, str_subtree=False)
            elif (advanced := _advance_field_type(node, part)) is not None:
                yield from walk(advanced, here, str_subtree=False)
            elif tag_fallback and part == union_tag and not getattr(node, _LOCALS_GRAFT, False):
                # The tag is the fallback, so it resolves only at a position no member
                # of its exact spelling reaches.
                yield from walk(str, here, str_subtree=True)
            elif tuple(parts[: len(stones)]) in calls:
                # A sibling of an opened call is an argument of its target, as below a callable.
                yield from walk(str, here, str_subtree=False)
            else:
                yield _Branch(here, None)

    yield from walk(_resolve_type(target), (), str_subtree=False)


def _field_types(
    target: Any,
    parts: list[str],
    union_tag: str,
    *,
    tag_fallback: bool = True,
    calls: Collection[tuple[str, ...]] = (),
) -> list[Any]:
    """Return the type each branch of the walk along *parts* reaches at its end.

    One type per branch of :func:`_walk_path` that accepts the whole path, in variant
    order; an empty list means no branch accepts it. :func:`_resolve_field_type` folds
    the list into the single type a value is coerced by; a caller that asks what each
    branch holds at a node -- the env channel spelling the next segment -- reads it whole.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.
        tag_fallback: Whether a segment no member reaches may still name the union tag.
        calls: The paths at which the command line opens a typed call.
    """
    branches = _walk_path(target, parts, union_tag, tag_fallback=tag_fallback, calls=calls)
    return [branch.end for branch in branches if branch.end is not None]


def _common_type(found: list[Any]) -> Any | None:
    """Fold the types the branches reach at one path into the type a value there is coerced by.

    Their common type when they all agree, ``str`` -- the raw token, left for construction
    to read by the variant it picks -- when they do not, and None when there is none.
    """
    if not found:
        return None
    first = found[0]
    return first if all(t == first for t in found[1:]) else str


def _resolve_field_type(
    target: Any,
    parts: list[str],
    union_tag: str,
    *,
    tag_fallback: bool = True,
    calls: Collection[tuple[str, ...]] = (),
) -> Any | None:
    """Return the type a value at the dotted path *parts* is coerced by, None if no branch accepts it.

    The fold (:func:`_common_type`) of :func:`_field_types` over the branches that accept
    the path.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.
        tag_fallback: Whether a segment no member reaches may still name the union tag.
        calls: The paths at which the command line opens a typed call.

    Returns:
        The resolved type at the end of the path, or None if the path is invalid.
    """
    return _common_type(_field_types(target, parts, union_tag, tag_fallback=tag_fallback, calls=calls))


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


def _addresses_callable_key(
    target: Any,
    parts: list[str],
    union_tag: str,
    *,
    calls: Collection[tuple[str, ...]] = (),
) -> bool:
    """Return True if the dotted path names a key *inside* a callable spec.

    Below a ``Callable`` field, everything is one answer, because everything below it is
    one dict the parser writes verbatim: a directive, a bind or call subkey in either
    spelling, or a sibling kwarg no signature names.  Which of those a key *is* — and
    whether it is acceptable — the opener decides at construction, and a path does not see
    the opener.  Below a field of any other type, the spec is a typed call: its ``call``
    key and what is below it, and a sibling of a call the command line opens (*calls*).

    The adapters register a flag on this answer alone, so the caller must strip an
    append/delete suffix first: those flags are registered when typed, in the shape
    their mode demands.

    Dev Notes:
        docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
    """
    return any(
        _is_callable(stone.node) or _opens_target(stone, part, k) or tuple(parts[:k]) in calls
        for branch in _walk_path(target, parts, union_tag, calls=calls)
        for k, (stone, part) in enumerate(zip(branch.stones, parts, strict=False))
    )


def _opener_at(target: Any, parts: list[str], union_tag: str) -> bool:
    """Return True if the last segment of *parts* is an opener of a spec at the path before it.

    Any opener, in either form, opens a spec on a callable field; ``call`` does on a field
    that takes a typed call (:func:`_opens_target`). A field named like an opener is no
    opener of its parent (BUG-30).
    """
    k = len(parts) - 1
    return (
        k >= 0
        and names_an_opener(parts[k])
        and any(
            len(branch.stones) > k
            and (_is_callable(branch.stones[k].node) or _opens_target(branch.stones[k], parts[k], k))
            for branch in _walk_path(target, parts, union_tag)
        )
    )


def _is_collection_patch_path(target: Any, parts: list[str], union_tag: str) -> bool:
    """Return True if the dotted path indexes a list/tuple/set or keys a dict.

    Such paths (e.g. ``users.0``, ``dbs.1.port``, ``foo.bar``) are open-ended, so no
    static walk can list them: the adapters register their flags when argv types them.
    Pure struct-field, namedtuple, and callable paths return False; a collection or a
    namespace below a namedtuple's field is a patch, as one below a struct's is.

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity
    """
    return any(
        _type_kind(stone.node) in _COLLECTION_KINDS or part in _locals_keys_nested(stone.node, union_tag)
        for branch in _walk_path(target, parts, union_tag)
        for stone, part in zip(branch.stones, parts, strict=False)
    )


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


def _path_unknown(target: Any, parts: list[str], union_tag: str, *, calls: Collection[tuple[str, ...]] = ()) -> bool:
    """Return True when *parts* names no node a flag can write: vanilla refuses it as unknown.

    A path the walk resolves is a member; a path below a dict-typed node is a key the dict
    takes, whatever it spells.  The delete handler, the unknown-field handler and the
    adapters' skip of the host's own flags all ask this one question.
    """
    return _resolve_field_type(target, parts, union_tag, calls=calls) is None and not _is_dict_at_path(
        target,
        parts,
        union_tag,
    )


def _typed_call_openings(
    target: Any,
    argv: Sequence[str],
    union_tag: str,
    config_flag: str,
) -> frozenset[tuple[str, ...]]:
    """Return the paths at which *argv* opens a ``call:`` on a field that is no ``Callable``.

    A field opens one where a ``call`` key, in either form, is a typed call there
    (:func:`_opens_target`), spelled by a flag (``--n.call pkg.f``, ``--n.call.classfn
    pkg.C.m``), by a key of a whole ``{…}`` value, or by a key of a root ``--<config_flag>``
    file argv names.  Below such a path, a segment no member reaches is an argument of the
    call's target (:func:`_walk_path`). *argv* has no CLI prefix left. Vanilla's loop and
    the adapters' registration both ask it, so a flag one accepts the other registers.

    Dev Notes:
        docs-dev/architecture/callables.md#cli
    """
    found: set[tuple[str, ...]] = set()
    for parts in _paths_argv_spells(argv, config_flag):
        for branch in _walk_path(target, parts, union_tag):
            for k, (stone, part) in enumerate(zip(branch.stones, parts, strict=False)):
                if not _is_callable(stone.node) and _opens_target(stone, part, k):
                    found.add(tuple(parts[:k]))
    return frozenset(found)


def _paths_argv_spells(argv: Sequence[str], config_flag: str) -> list[list[str]]:
    """Return every path *argv* writes: its flags', each key of a whole ``{…}`` value, each key of a root config file.

    A best-effort scan, as the tag scan's: a value that does not parse, or a file that does
    not load, spells nothing here, and the real error belongs to the parse.
    """
    paths: list[list[str]] = []

    def add_leaves(prefix: list[str], value: Any) -> None:
        if isinstance(value, dict) and value:
            for key, sub in value.items():
                add_leaves([*prefix, str(key)], sub)
        else:
            paths.append(prefix)

    args = _normalize_eq_args(argv)
    for i, token in enumerate(args):
        if not _looks_like_flag(token) or _addresses_key(token[2:], config_flag):
            continue
        path = _parse_flag_mode(token[2:])[0]
        paths.append(path)
        value = args[i + 1] if i + 1 < len(args) else ""
        if not _looks_like_flag(value) and value.startswith("{"):
            with contextlib.suppress(ValueError):
                add_leaves(path, json.loads(value))
    if config_flag:
        add_leaves([], _partial_config_from_argv(args, config_flag))
    return paths


def _is_dict_at_path(target: Any, parts: list[str], union_tag: str) -> bool:
    """Check if any branch of the walk stands on a dict at a non-empty proper prefix of the path.

    The node a branch stands on, not the type the prefix reaches: a field typed
    ``dict[str, Any] | None`` or ``dict[str, Any] | Inner`` reaches the union, and its dict
    variant takes what is below as a key, as a plain dict field and the environment do
    (BUG-158). A branch that refuses the path at a sequence below the dict takes nothing
    (:func:`_refuses_at_a_sequence`): its segment is no key of the dict but a patch key of
    the sequence, which the merge would read as its own (BUG-170).

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to check.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        True if a branch stands on a dict type at any non-empty proper prefix of parts.

    Dev Notes:
        docs-dev/architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions
    """
    return any(
        not _refuses_at_a_sequence(branch) and any(_is_dict(stone.node) for stone in branch.stones[1:])
        for branch in _walk_path(target, parts, union_tag)
    )


def _sequence_refusal(target: Any, parts: list[str], union_tag: str) -> int | None:
    """Return the position in *parts* of the segment a sequence refuses, None if the path is no such refusal.

    A refusal only when vanilla's loop refuses the path (:func:`_path_unknown`), and a branch
    of the walk refused it standing on a sequence (:func:`_refuses_at_a_sequence`): the
    environment, which leaves any other unknown path below its first segment to ``build()``,
    asks it to keep a segment from reaching the merge as a list-patch key (BUG-170).

    Dev Notes:
        docs-dev/architecture/cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index
    """
    if not _path_unknown(target, parts, union_tag):
        return None
    refused = (len(b.stones) - 1 for b in _walk_path(target, parts, union_tag) if _refuses_at_a_sequence(b))
    return next(refused, None)


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
    :data:`~confarg._cast.FORCE_CAST_NAMES`, it does not name a real field/key of
    the parent (real field wins), and the parent's type holds the cast's type —
    a cast naming anything else would place a value the field does not accept,
    so the key keeps its path and the walk refuses it as unknown, exactly as the
    adapters' registration never offers it.  Otherwise ``(path, None)``.  A
    root-level cast (no parent to attach to) is a cast only for ``--json``
    (whole-config injection, empty returned path); root-level scalar casts have
    no struct to attach to and are ignored.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds
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
    branch_types = _field_types(target, parent, union_tag)
    parent_type = _common_type(branch_types)
    if parent_type is None or _segment_names_real_field(parent_type, path[-1], union_tag):
        return path, None
    # Each branch is asked what it holds, never the fold: branches that disagree fold to
    # `str`, which holds no other cast, where the variant construction picks may (BUG-214).
    cast_tp = SCALAR_CAST_TYPES.get(path[-1])
    if cast_tp is not None and not any(holds_the_cast(t, cast_tp) for t in branch_types):
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


def _fixed_arity_usage(tp: Any) -> str:
    """Return the usage a fixed-arity flag's missing value spells: one placeholder per position.

    A namedtuple's position is named by its field, as its ``--<flag>.<field>`` sub-flag
    names it (``<x> <y>``); a ``tuple[X, Y]`` has no names, so each position is a
    ``<value>``.  The one spelling, for vanilla's loop (:func:`_consume_fixed_tuple_args`)
    and for the spec a front-end refuses a bare occurrence from
    (:attr:`~confarg.cli.FlagSpec.usage`), so the two cannot disagree (BUG-171).

    Args:
        tp: A type :func:`~confarg._types._fixed_seq_types` gives a fixed arity.

    Returns:
        The placeholders, space-separated.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    tp = _resolve_type(tp)
    if _is_namedtuple(tp):
        return " ".join(f"<{name}>" for name in _namedtuple_fields(tp))
    return " ".join("<value>" for _ in _fixed_seq_types(tp) or ())


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


def _reserved_segment(path: Sequence[str]) -> str | None:
    """Return the first segment of *path* spelling a key confarg reserves, or ``None``.

    The one test a flag's path, an environment variable's and a mount point's are put to: none
    of them may write a key the merge or ``build()`` reads as its own
    (``_defaults.RESERVED_KEYS``), which only a configuration file writes.

    Dev Notes:
        docs-dev/architecture/config-files/reserved-keys.md#reserved-file-only-keys
    """
    return next((seg for seg in path if seg in _defaults.RESERVED_KEYS), None)


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


def _strip_argv_prefix(argv: Sequence[str], cli_prefix: str) -> list[str]:
    """Return *argv* with *cli_prefix* removed from its flags, dropping foreign tokens.

    The implementation of :func:`~confarg.cli._prefix.strip_argv_prefix`, here so that
    vanilla's loop can strip the argv its scans read without importing the adapters.
    """
    if not cli_prefix:
        return list(argv)
    args = _normalize_eq_args(list(argv))
    dot_pfx = f"{cli_prefix}."
    out: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if not _looks_like_flag(token) or not token[2:].startswith(dot_pfx):
            i = _skip_flag_values(args, i) if _looks_like_flag(token) else i + 1
            continue
        out.append(f"--{token[2:].removeprefix(dot_pfx)}")
        i += 1
        while i < len(args) and not _looks_like_flag(args[i]):
            out.append(args[i])
            i += 1
    return out


_LOCALS_GRAFT = "_confarg_locals_graft"


@functools.cache
def _locals_walk_root(locals_keys: tuple[str, ...]) -> Any:
    """Return a dataclass with one ``dict[str, Any]`` field per local-variables key.

    Grafted onto the walk target by :func:`_walk_target` so ``--<key>.<name>`` paths
    resolve like a real dict field. It answers those keys and nothing else: no class is
    dispatched on it, so :func:`_walk_path` never answers the union tag at it.
    Validation happens in the pipeline, not here.

    Dev Notes:
        docs-dev/architecture/locals.md#walk-target-graft
    """
    name = "_LocalsRoot_" + "_".join(locals_keys)
    fields = [(key, dict[str, Any]) for key in locals_keys]
    return dataclasses.make_dataclass(name, fields, namespace={_LOCALS_GRAFT: True})


def _walk_target(target: Any, locals_keys: tuple[str, ...]) -> Any:
    """Return the target to resolve dotted paths against, with the locals namespace grafted on.

    A non-struct root is set whole, from ``__root__``, so no dotted path reaches into its
    value: its walk target is the locals namespace beside it, alone. Use the result *only*
    for path resolution; classify the root (scalar vs struct) and check config-flag
    conflicts against the real ``target``. *locals_keys* must come from
    :func:`_locals_keys`: grafting a name that is also a real field silently routes
    ``--<name>.x`` away from that field. Nested namespaces are handled by
    :func:`_resolve_field_type` itself.

    Dev Notes:
        docs-dev/architecture/cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole
    """
    if not _is_struct_like(_resolve_type(target)):
        return _locals_walk_root(locals_keys)
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
    key = key.removesuffix(APPEND_SUFFIX)
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
        return key.removeprefix(f"{config_flag}.")
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
        ConfargError: When the subpath names no field of the node it descends to, or a
            segment spells a key confarg reserves (:func:`_reserved_segment`).

    Dev Notes:
        docs-dev/architecture/cli-parsing/type-guided-parsing.md#type-guided-parsing
    """
    path = subpath.removesuffix(APPEND_SUFFIX)
    if not path:
        return
    parts = path.split(".")
    if (reserved := _reserved_segment(parts)) is not None:
        raise ConfargError.reserved_key(spelling, reserved)
    walk_target = _walk_target(target, _locals_keys(target, union_tag))
    for j in range(1, len(parts) + 1):
        if _resolve_field_type(walk_target, parts[:j], union_tag) is not None:
            continue
        if j == 1 and not _is_struct_like(_resolve_type(target)):
            name = _mount_owner(target)[0]
            raise ConfargError.mount_below_a_value_root(spelling, name, _defaults.ROOT_KEY)
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

    append_mode = bool(path) and path[-1].endswith(APPEND_SUFFIX) and len(path[-1]) > 1
    if append_mode:
        path[-1] = path[-1][:-1]

    delete_mode = not append_mode and bool(path) and path[-1].endswith(DELETE_SUFFIX) and len(path[-1]) > 1
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
    #: The paths at which argv opens a typed call (:func:`_typed_call_openings`).
    calls: frozenset[tuple[str, ...]] = frozenset()
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
        if _path_unknown(ctx.target, path, ctx.union_tag, calls=ctx.calls):
            raise UnknownArgumentError.not_indexable(token, parent_path)
        node: Any = ctx.data
        for _p in parent_path:
            node = node[_p] if isinstance(node, dict) and _p in node else {}
        del_key = LIST_POST_APPEND_DELETE_KEY if isinstance(node, dict) and LIST_APPEND_KEY in node else LIST_DELETE_KEY
        _accumulate_list_delete(ctx.data, parent_path, delete_idx, token, delete_key=del_key)
    else:
        if _path_unknown(ctx.target, path, ctx.union_tag, calls=ctx.calls):
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
    """Combine append_items with what the path holds, opened as any op below it opens it.

    So an append after a whole value extends that value, and one after a whole-field delete
    extends nothing (:func:`~confarg._merge._open_for_ops`).
    """
    node = _open_for_ops(existing)
    return {**node, LIST_APPEND_KEY: node.get(LIST_APPEND_KEY, []) + append_items}


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


def _consume_fixed_tuple_args(  # noqa: PLR0913, PLR0917  # token only names the flag in the error
    args: Sequence[str],
    i: int,
    token: str,
    ft: Any,
    path: list[str],
    data: dict[str, Any],
) -> int:
    """Consume exactly one argument per position of the fixed-length sequence *ft*.

    Every one of them is required: a fixed arity is not a shape a bare flag is reserved
    for, so argv running short -- or reaching the next flag -- is a missing value and not
    a shorter tuple (BUG-43), whose usage spells every position (BUG-171).

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    usage = _fixed_arity_usage(ft)
    items: list[Any] = []
    for et in _fixed_seq_types(ft) or ():
        _require_value(args, i, token, usage)
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
    A single none word the union reads as ``None`` is stored bare too, the
    environment's shape, so ``--xs none`` nulls a ``list[int] | None`` as
    ``APP_XS=none`` does (BUG-163). Otherwise the tokens form a list and tuple/list/set disambiguation is
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
    if len(tokens) == 1 and _selects_none(_union_args(ft), _StrToken(tokens[0])):
        return _StrToken(tokens[0])
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


def _handle_force_cast(  # noqa: PLR0913, PLR0917  # cast_name is a necessary discriminator, not incidental
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

    A path below a dict is a key, which takes its value as any value-taking flag does
    (:func:`_require_value`, BUG-161); the new index is returned. No declaration types the
    key, so its append is :func:`_handle_append_token`'s to refuse, as for an ``Any`` value
    one segment up (BUG-166). Otherwise always raises UnknownArgumentError.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    if _is_dict_at_path(ctx.target, path, ctx.union_tag):
        if append_mode:
            return _handle_append_token(ctx, i + 1, token, Any, path)
        _require_value(ctx.argv, i + 1, token)
        _set_nested(ctx.data, path, _StrToken(ctx.argv[i + 1]))
        return i + 2
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
        return _consume_fixed_tuple_args(args, i, token, ft, path, ctx.data)

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

    ``--fn pkg.func`` is the shorthand for ``--fn.bind pkg.func``, so a later
    ``--fn.<param>`` must refine the target the shorthand named, not erase it.  This is
    the one place that decides it, for every channel: the CLI parse loop and the env parse
    loop both call it before they store, so ``FN=pkg.func`` plus ``FN__SEP=-`` reads
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
    calls = _typed_call_openings(walk_target, _strip_argv_prefix(argv, cli_prefix), union_tag, config_flag)
    ctx = _ParseCtx(argv=argv, target=walk_target, union_tag=union_tag, calls=calls)
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

        if (reserved := _reserved_segment(path)) is not None:
            raise ConfargError.reserved_key(token, reserved)

        # A bare callable shorthand already stored at a prefix of this path is a spec, not
        # a stale scalar: open it so this flag refines it
        # (docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption).
        _open_callable_shorthand(ctx.data, path, walk_target, union_tag)

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

        ft = _resolve_field_type(walk_target, path, union_tag, calls=ctx.calls)
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

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

import dataclasses
import enum
import functools
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple, NoReturn

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

from confarg import _defaults
from confarg._callable import (
    _COMPUTATION_OPENERS,
    _OBJECT_OPENERS,
    _competing_openers,
    names_an_opener,
    opens_a_subtree,
    promote_bare_spec,
)
from confarg._cast import (
    FORCE_CAST_NAMES,
    JSON_CAST_NAME,
    SCALAR_CAST_TYPES,
    decode_json,
    fold_root_json,
    holds_the_cast,
    resolve_forced_value,
)
from confarg._depth import refuse_long_path
from confarg._merge import (
    APPEND_SUFFIX,
    DELETE_SUFFIX,
    DICT_DELETE,
    ListOp,
    MergeAt,
    MergeDict,
    _accumulate_list_delete,
    _open_for_ops,
    _peek_nested,
    _set_nested,
)
from confarg._naming import (
    TARGET,
    Named,
    is_arguments,
    named_child,
    named_variant,
    names_something,
    node_at,
    opener_keys,
    takes_untyped_argument,
)
from confarg._tags import import_tagged_classes
from confarg._types import (
    _dict_kv,
    _elem_type,
    _fixed_position,
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
    _union_branches,
    _union_has_scalar_variant,
    _union_has_seq_variant,
    _union_has_varlen_variant,
    _UnionSeqToken,
)
from confarg.dictexpr._expressions import _list_index
from confarg.exceptions import ConfargError, UnknownArgumentError
from confarg.typedload._coerce import _try_coerce, _type_kind, _TypeKind
from confarg.typedload._construct import _is_typed_call, _reads_specs, _selects_none, _takes_typed_call

#: What the data a path is typed against names at a node, by the node's path: the dict the
#: node holds, or None where nothing names it (:func:`_walk_path`).
NamingView = Callable[[tuple[str, ...]], Any]


def _step_tuple_type(tp: Any, part: str) -> Any | None:
    """Advance one step into a tuple type by numeric index.

    A variadic tuple takes an index as a list does, only as ``str()`` writes one; a fixed
    tuple takes a position as a namedtuple does (:func:`~confarg._types._fixed_position`,
    BUG-108).
    """
    et = _tuple_types(tp)
    if et is None:
        return _elem_type(tp) if _list_index(part) is not None else None
    position = _fixed_position(tp, part)
    return None if position is None else et[position]


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
            position = _fixed_position(tp, part)
            return None if position is None else list(_namedtuple_fields(tp).values())[position]
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
        case _TypeKind.ANY:
            # A keyed Any is a dict[Any, Any]: an opener, a field of the class it names, an
            # argument under args or a plain key, each an Any node in turn.
            return Any
        case _TypeKind.UNION | _TypeKind.LEAF:
            return None


class _Stone(NamedTuple):
    """Where a way of the walk (:func:`_walk_path`) stands to step along one path segment."""

    #: The type the walk reached here, a union unexpanded: what a walk of the path so far answers.
    reached: Any
    #: The resolved, non-union type this way takes ``reached`` as.
    node: Any


class _Edge(NamedTuple):
    """One way the walk steps along a path segment: from a state, standing on a stone, to where it lands."""

    #: The state the walk stood in before the segment.
    before: _WalkState
    #: Where it stood to step: the type reached, and the variant this way takes it as.
    stone: _Stone
    #: The state it lands on; None when this way refuses the segment.
    after: _WalkState | None


class _Walk(NamedTuple):
    """The walk of a path (:func:`_walk_path`): each way it steps along each segment, from each state once."""

    #: The state the walk starts in, at the root.
    start: _WalkState
    #: ``layers[k]``: the edges stepping along ``parts[k]`` from each state the walk reached before it.
    layers: list[list[_Edge]]

    def edges(self) -> Iterator[tuple[int, _Edge]]:
        """Yield each edge with the position of the segment it steps along, segment by segment."""
        for k, layer in enumerate(self.layers):
            for edge in layer:
                yield k, edge

    def ends(self) -> list[Any]:
        """Return the type each way accepting the whole path reaches, a union unexpanded, each once."""
        return [state.reached for state in (_landed(self.layers[-1]) if self.layers else [self.start])]

    def edges_on_ways(self, counted: Callable[[_Edge], bool]) -> Iterator[tuple[int, _Edge]]:
        """Yield each edge on a way that accepts the whole path or ends on a refusal *counted* accepts.

        The questions that read a way's history ask it: what a way stood on before its end
        counts only if the end does. Walked back from the last segment, keeping the states
        from which the rest of the path reaches such an end.
        """
        kept: list[list[_Edge]] = []
        leading: list[_WalkState] | None = None  # past the last segment, every state is an end
        for layer in reversed(self.layers):
            on_way = [e for e in layer if (counted(e) if e.after is None else leading is None or e.after in leading)]
            kept.append(on_way)
            leading = _distinct(e.before for e in on_way)
        for k, layer in enumerate(reversed(kept)):
            for edge in layer:
                yield k, edge


#: The kinds whose patch is a list patch: the merge reads every key below one as an index or as
#: one of its own list-patch keys, a namedtuple's field names aside.
_SEQUENCE_KINDS = frozenset(
    {_TypeKind.LIST, _TypeKind.SET, _TypeKind.FROZENSET, _TypeKind.TUPLE, _TypeKind.NAMEDTUPLE},
)

#: The kinds a collection patch stands on: the merge reads every key below one as an index,
#: an op or a dict key. A namedtuple is none of them: the static walk lists its own fields
#: and indices (BUG-157). A keyed ``Any`` is a ``dict[Any, Any]``, whose keys no walk lists.
_COLLECTION_KINDS = frozenset(
    {_TypeKind.LIST, _TypeKind.SET, _TypeKind.FROZENSET, _TypeKind.TUPLE, _TypeKind.DICT, _TypeKind.ANY},
)


def _refuses_at_a_sequence(edge: _Edge) -> bool:
    """Return True if *edge* refuses its segment standing on a sequence, the segment naming no element of it.

    Dev Notes:
        docs-dev/architecture/cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index
    """
    return edge.after is None and _type_kind(edge.stone.node) in _SEQUENCE_KINDS


def _opens_spec_subtree(stone: _Stone, part: str, depth: int) -> bool:
    """Return True if *part*, met at *stone*, holds a subtree of a computation's spec.

    A ``bind`` or ``call`` target is a dotted path (``--f.call pkg.g``) or a callable spec of
    its own, addressable key by key (``--f.call.classfn pkg.C.m``), and ``args`` holds the
    target's arguments by name (``--f.args.sep -``), whatever their names
    (:func:`~confarg._callable.opens_a_subtree`). All three open one below a callable field;
    ``call`` and ``args`` below a field that takes a typed call, unless a member holds the
    name (:func:`~confarg.typedload._construct._takes_typed_call`), so ``--n.args.x`` needs
    no opener on the command line. The root (*depth* 0) holds no typed call: its flags share
    the namespace with a host framework's own, and nor does the mapping under ``args``,
    whose keys are a target's parameters.

    Dev Notes:
        docs-dev/architecture/callables.md#cli
    """
    if _is_callable(stone.node):
        return opens_a_subtree(part)
    return (
        depth > 0
        and part in (_defaults.CALL_KEY, _defaults.ARGS_KEY)
        and not is_arguments(stone.node)
        and _takes_typed_call(stone.reached, part)
    )


def _unnamed_spec_step(stone: _Stone, part: str, depth: int) -> Any:
    """Return the type of *part* below a spec node that names nothing yet, or :attr:`Named.NOTHING` for no spec node.

    Below a Callable or an ``Any``, an object opener's value is a dotted-path leaf, a
    computation opener's a target spec of its own, and ``args`` the arguments of a target no
    opener names, untyped at any depth. Any other key below a Callable is a field of a class
    no opener names yet, untyped at any depth too (BUG-233); below an ``Any`` it is an ``Any``
    node. Below a field that takes a typed call (:func:`_opens_spec_subtree`), ``call`` is a
    target and ``args`` untyped.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#no-naming-known
    """
    kind = _type_kind(stone.node)
    if kind in (_TypeKind.CALLABLE, _TypeKind.ANY):
        if part in _OBJECT_OPENERS:
            return str
        if part in _COMPUTATION_OPENERS:
            return TARGET
        return Named.UNTYPED if kind is _TypeKind.CALLABLE or part == _defaults.ARGS_KEY else Named.NOTHING
    if _opens_spec_subtree(stone, part, depth):
        return TARGET if part == _defaults.CALL_KEY else Named.UNTYPED
    return Named.NOTHING


def _opens_a_spec(node: Any, naming: Any) -> bool:
    """Return whether a key below the node *node*, holding *naming*, is read by a spec: no namespace lies below it."""
    if _type_kind(node) in (_TypeKind.CALLABLE, _TypeKind.ANY) or is_arguments(node):
        return True
    return naming is not None and _is_typed_call(naming, node)


def _walk_path(
    target: Any,
    parts: list[str],
    union_tag: str,
    *,
    tag_fallback: bool = True,
    named: NamingView | None = None,
) -> _Walk:
    """Walk the type tree along *parts*, segment by segment, each state the walk reaches stepped once.

    The one type walk. A union met before the path ends is stepped once per non-None
    variant, so the walk forks there, in variant order; but the ways that land on the same
    state go on as one, so a union met at every level costs the walk a step per variant, not
    a branch per choice of variants. A way that refuses a segment ends there, and a path
    ending *on* a union-typed node ends on that union, unexpanded. Every question about a
    path is asked of the walk: :func:`_field_types` reads its ends, the predicates over a
    path -- :func:`_addresses_callable_key`, :func:`_is_collection_patch_path` -- the
    stones its edges stood on, and :func:`_is_dict_at_path` those on the ways that end
    as it counts (:meth:`_Walk.edges_on_ways`).

    A node whose data names a class (*named*) types the segment below it by that class
    (:func:`~confarg._naming.named_child`), and a union naming one of its variants walks
    that variant alone (:func:`~confarg._naming.named_variant`). A segment names the union
    tag only when no real member of that exact spelling exists at its position; a field
    named like the tag is that field, and the tag's value is a leaf.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.
        tag_fallback: Whether a segment no member reaches may still name the union tag.
            Off, the walk answers members only, which is how
            :func:`_names_tag_by_fallback` tells the two apart.
        named: What the data the path is typed against names at each node; None types
            the path by the declared types alone.

    Dev Notes:
        docs-dev/architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions
    """
    start = _walk_start(target)
    states, layers = [start], []
    for k, part in enumerate(parts):
        naming = None if named is None or not states else named(tuple(parts[:k]))
        layer = _step_edges(states, part, k, naming, union_tag, tag_fallback=tag_fallback)
        layers.append(layer)
        states = _landed(layer)
    return _Walk(start, layers)


class _WalkState(NamedTuple):
    """Where the walk stands between two segments: all that the next step reads of what came before."""

    #: The type reached so far, a union unexpanded.
    reached: Any
    #: Whether every segment from here on is an untyped token: the walk is below one no type describes.
    str_subtree: bool
    #: Whether the walk is below a spec, where no ``locals`` namespace lies.
    in_spec: bool


def _walk_start(target: Any) -> _WalkState:
    """Return the state the walk of a path from *target*'s root starts in."""
    return _WalkState(_resolve_type(target), str_subtree=False, in_spec=False)


def _step(  # noqa: C901, PLR0913  # one answer per kind of step; where the walk stands and what names it
    state: _WalkState,
    part: str,
    depth: int,
    naming: Any,
    union_tag: str,
    *,
    tag_fallback: bool = True,
) -> Iterator[tuple[_Stone, _WalkState | None]]:
    """Step the walk along *part*, met at *depth*, yielding where it stands and where it lands, per way it can.

    The one step of the walk (:func:`_walk_path`): a union is taken once per non-None variant,
    or as the one variant *naming* names; a way that refuses *part* lands on None.
    *naming* is the dict the node at that position holds, or None where the data names nothing.
    A segment addressing a ``locals`` namespace (:func:`_locals_keys_nested`, of the type
    reached, whatever variant a way takes) lands on ``dict[str, Any]``.

    Dev Notes:
        docs-dev/architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions
    """
    naming = None if state.str_subtree else _naming_read_at(naming, depth)
    variant = None if naming is None else named_variant(state.reached, naming, union_tag)
    names = () if state.in_spec or state.str_subtree else _locals_keys_nested(state.reached, union_tag=union_tag)
    for node in [variant] if variant is not None else _union_branches(state.reached):
        stone = _Stone(state.reached, node)
        if state.str_subtree:
            yield stone, _WalkState(str, str_subtree=True, in_spec=True)
            continue
        if part in names:
            yield stone, _WalkState(dict[str, Any], str_subtree=False, in_spec=False)
            continue
        answer = Named.NOTHING if naming is None else named_child(node, part, naming, union_tag)
        if answer is Named.NOTHING:
            answer = _unnamed_spec_step(stone, part, depth)
        below_spec = state.in_spec or _opens_a_spec(node, naming)
        if answer is Named.REFUSED:
            yield stone, None
        elif answer is Named.UNTYPED:
            yield stone, _WalkState(str, str_subtree=True, in_spec=True)
        elif answer is not Named.NOTHING:
            yield stone, _WalkState(answer, str_subtree=False, in_spec=below_spec)
        elif (advanced := _advance_field_type(node, part)) is not None:
            yield stone, _WalkState(advanced, str_subtree=False, in_spec=below_spec)
        elif tag_fallback and part == union_tag and not _synthesized(node):
            # The tag is the fallback, so it resolves only at a position no member of its
            # exact spelling reaches; its value is a class path, below which nothing lies.
            yield stone, _WalkState(str, str_subtree=False, in_spec=below_spec)
        elif takes_untyped_argument(node, part):
            yield stone, _WalkState(str, str_subtree=True, in_spec=True)
        else:
            yield stone, None


def _naming_read_at(naming: Any, depth: int) -> MergeDict | None:
    """Return what of *naming*, the data at a node *depth* below the root, may name what it builds; None for no dict."""
    if not isinstance(naming, dict):
        return None
    if depth == 0:
        # The root holds no typed call: its flags share the namespace with a host's own.
        return {key: v for key, v in naming.items() if key not in (_defaults.CALL_KEY, _defaults.ARGS_KEY)}
    return naming


def _synthesized(node: Any) -> bool:
    """Return whether *node* is a class confarg builds for the walk alone, which no tag dispatches on."""
    return bool(getattr(node, _LOCALS_GRAFT, False)) or is_arguments(node)


def _field_types(
    target: Any,
    parts: list[str],
    union_tag: str,
    *,
    tag_fallback: bool = True,
    named: NamingView | None = None,
) -> list[Any]:
    """Return the type each branch of the walk along *parts* reaches at its end.

    One type per way of :func:`_walk_path` that accepts the whole path, each type once, in
    variant order; an empty list means no way accepts it. :func:`_resolve_field_type` folds
    the list into the single type a value is coerced by; a caller that asks what each
    branch holds at a node -- the env channel spelling the next segment -- reads it whole.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.
        tag_fallback: Whether a segment no member reaches may still name the union tag.
        named: What the data the path is typed against names at each node (:func:`_walk_path`).
    """
    return _walk_path(target, parts, union_tag, tag_fallback=tag_fallback, named=named).ends()


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
    named: NamingView | None = None,
) -> Any | None:
    """Return the type a value at the dotted path *parts* is coerced by, None if no branch accepts it.

    The fold (:func:`_common_type`) of :func:`_field_types` over the branches that accept
    the path.

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to follow.
        union_tag: The field name used as a discriminator tag in unions.
        tag_fallback: Whether a segment no member reaches may still name the union tag.
        named: What the data the path is typed against names at each node (:func:`_walk_path`).

    Returns:
        The resolved type at the end of the path, or None if the path is invalid.
    """
    return _common_type(_field_types(target, parts, union_tag, tag_fallback=tag_fallback, named=named))


def _names_tag_by_fallback(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> bool:
    """Return True if the path's last segment is the union tag, reached by the walk's fallback.

    The walk's own answer: the path resolves with the tag rule and does not without it,
    so a member spelled like the tag -- a field, a subclass-only field, a callable's
    directive -- is never mistaken for the tag.
    """
    return (
        bool(parts)
        and parts[-1] == union_tag
        and _resolve_field_type(target, parts, union_tag, named=named) is not None
        and _resolve_field_type(target, parts, union_tag, tag_fallback=False, named=named) is None
    )


def _addresses_callable_key(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> bool:
    """Return True if the dotted path names a key *inside* a callable spec.

    Below a ``Callable`` field, everything is one answer, because everything below it is
    one dict the parser writes verbatim: an opener, a key of a nested target spec, an
    argument under ``args``, or a field of a ``class`` no signature names.  Which of those a
    key *is* — and whether it is acceptable — the opener decides at construction, and a path
    does not see the opener.  Below a field of any other type, the spec is a typed call: its
    ``call`` and ``args`` keys and what is below them (:func:`_opens_spec_subtree`).

    The adapters register a flag on this answer alone, so the caller must strip an
    append/delete suffix first: those flags are registered when typed, in the shape
    their mode demands.

    Dev Notes:
        docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
    """
    return any(
        _is_callable(e.stone.node) or _opens_spec_subtree(e.stone, parts[k], k)
        for k, e in _walk_path(target, parts, union_tag, named=named).edges()
    )


def _opener_at(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> bool:
    """Return True if the last segment of *parts* opens a spec at the path before it (:func:`_opener_reader_at`)."""
    return _opener_reader_at(target, parts, union_tag, named) is not None


def _opener_reader_at(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> Any:
    """Return the type reading the last segment of *parts* as an opener of a spec at the path before it, or None.

    A Callable or an ``Any`` node reads every opener, a nested target spec's Callable
    included; ``call`` opens a typed call on a field that takes one
    (:func:`_opens_spec_subtree`), and a typed call's value is the type reached there's, a
    union's beside its Callable too. A field named like an opener is no opener of its parent
    (BUG-30), and a key under ``args`` is a parameter's name, the arguments of a target no
    opener names included, whose keys the walk reads as they are written.

    Dev Notes:
        docs-dev/architecture/callables.md#cli
    """
    k = len(parts) - 1
    if k < 0 or not names_an_opener(parts[k]):
        return None
    for e in _walk_path(target, parts, union_tag, named=named).layers[k]:
        if e.before.str_subtree or not (_reads_specs(e.stone.node) or _opens_spec_subtree(e.stone, parts[k], k)):
            continue
        if parts[k] == _defaults.CALL_KEY and _takes_typed_call(e.stone.reached):
            return e.stone.reached
        return e.stone.node
    return None


def _is_collection_patch_path(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> bool:
    """Return True if the dotted path indexes a list/tuple/set or keys a dict.

    Such paths (e.g. ``users.0``, ``dbs.1.port``, ``foo.bar``) are open-ended, so no
    static walk can list them: the adapters register their flags when argv types them.
    Pure struct-field, namedtuple, and callable paths return False; a collection or a
    namespace below a namedtuple's field is a patch, as one below a struct's is.

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity
    """
    return any(
        _type_kind(e.stone.node) in _COLLECTION_KINDS
        or parts[k] in _locals_keys_nested(e.stone.reached, union_tag=union_tag)
        for k, e in _walk_path(target, parts, union_tag, named=named).edges()
    )


def _registered_when_typed(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> bool:
    """Return True if the adapters register this path's flag only when argv types it.

    A collection patch (:func:`_is_collection_patch_path`), or a union tag the walk
    reaches by its fallback (:func:`_names_tag_by_fallback`) -- whatever the parent, as
    vanilla's tag rule answers whatever the parent.  The static walk lists neither, so
    the argv scan registers them, and the loop that writes the adapters' CLI channel
    writes them as it writes any flag, in the order argv spells it.

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity
    """
    return _is_collection_patch_path(target, parts, union_tag, named) or _names_tag_by_fallback(
        target,
        parts,
        union_tag,
        named,
    )


def _path_unknown(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> bool:
    """Return True when *parts* names no node a flag can write: vanilla refuses it as unknown.

    A path the walk resolves is a member; a path below a dict-typed node is a key the dict
    takes, whatever it spells.  The delete handler, the unknown-field handler and the
    adapters' skip of the host's own flags all ask this one question.
    """
    return _resolve_field_type(target, parts, union_tag, named=named) is None and not _is_dict_at_path(
        target,
        parts,
        union_tag,
        named,
    )


def _is_dict_at_path(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> bool:
    """Check if any way of the walk stands on a dict at a non-empty proper prefix of the path.

    The node a way stands on, not the type the prefix reaches: a field typed
    ``dict[str, Any] | None`` or ``dict[str, Any] | Inner`` reaches the union, and its dict
    variant takes what is below as a key, as a plain dict field and the environment do
    (BUG-158). A way that refuses the path at a sequence below the dict takes nothing
    (:func:`_refuses_at_a_sequence`): its segment is no key of the dict but a patch key of
    the sequence, which the merge would read as its own (BUG-170).

    Args:
        target: The root type to start resolution from.
        parts: A list of path segments to check.
        union_tag: The field name used as a discriminator tag in unions.
        named: What the data the path is typed against names at each node (:func:`_walk_path`).

    Returns:
        True if a way stands on a dict type at any non-empty proper prefix of parts.

    Dev Notes:
        docs-dev/architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions
    """
    walk = _walk_path(target, parts, union_tag, named=named)
    return any(
        k >= 1 and _is_dict(e.stone.node)
        for k, e in walk.edges_on_ways(lambda refusal: not _refuses_at_a_sequence(refusal))
    )


class _Unreached(enum.Enum):
    """Why a path names nothing a flag writes: the cause both channels spell their refusal of it by."""

    NAMELESS = enum.auto()  # it ends in no name: nothing, ``+`` or ``-`` after its last separator
    NO_ELEMENT = enum.auto()  # a segment below a sequence names no element of it
    NOT_FOUND = enum.auto()  # any other segment names no member


#: The last segments that name nothing: a path ending in its separator, or in a suffix with no name before it.
_NAMELESS_SEGMENTS = frozenset({"", APPEND_SUFFIX, DELETE_SUFFIX})


def _unreached(
    target: Any,
    parts: list[str],
    union_tag: str,
    named: NamingView | None = None,
) -> tuple[_Unreached, int] | None:
    """Return why *parts* names nothing a flag writes and the position of its segment at fault, None if it names one.

    Asked only when vanilla's loop refuses the path (:func:`_path_unknown`): by that loop for
    an unknown flag, and by the environment for a variable below its first segment, so a
    flag and a variable of one path are refused for one cause (BUG-265). A last segment
    naming nothing (:data:`_NAMELESS_SEGMENTS`) is a missing name; a segment a way of the walk
    refuses standing on a sequence (:func:`_refuses_at_a_sequence`) names no element, which
    stored would reach the merge as a list-patch key (BUG-170), the shallowest one where
    several ways refuse so; any other path names no member, its last segment at fault.

    Dev Notes:
        docs-dev/architecture/environment-parsing.md#a-path-no-flag-reaches-is-refused-below-the-first-segment
        docs-dev/architecture/cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index
    """
    if not _path_unknown(target, parts, union_tag, named):
        return None
    if len(parts) > 1 and parts[-1] in _NAMELESS_SEGMENTS:
        return _Unreached.NAMELESS, len(parts) - 1
    walk = _walk_path(target, parts, union_tag, named=named)
    at = next((k for k, e in walk.edges() if _refuses_at_a_sequence(e)), None)
    return (_Unreached.NOT_FOUND, len(parts) - 1) if at is None else (_Unreached.NO_ELEMENT, at)


def _refuse_unreached_flag(token: str, path: list[str], unreached: tuple[_Unreached, int] | None) -> NoReturn:
    """Refuse the flag *token*, whose *path* names nothing a flag writes, for the cause :func:`_unreached` gave.

    Raises:
        UnknownArgumentError: Always.
    """
    cause, at = unreached or (_Unreached.NOT_FOUND, len(path) - 1)
    if cause is _Unreached.NAMELESS:
        raise UnknownArgumentError.missing_field_name(token[: token.rfind(".") + 1])
    if cause is _Unreached.NO_ELEMENT:
        raise UnknownArgumentError.no_element(token, path[at], ".".join(path[:at]))
    raise UnknownArgumentError.no_such_field(token, path)


#: The kinds whose members are named: a segment below one names a key, never an index.
_KEYED_KINDS = frozenset({_TypeKind.DICT, _TypeKind.STRUCT, _TypeKind.TAGGABLE_LEAF})


def _delete_index(target: Any, parts: list[str], union_tag: str, named: NamingView | None = None) -> int | None:
    """Return the index a delete at *parts* removes, None when it removes the key its last segment names.

    The one decoder of a delete's last segment, for a flag (``--xs.1-``) and a variable
    (``XS__1-``) alike. A segment spelling no index as ``str()`` writes one
    (:func:`~confarg.dictexpr._expressions._list_index`) is a key. One spelling an index is a
    key where every branch of the walk taking the path stands on a dict, a struct or a
    fixed-length sequence, whose position a delete unsets in place (BUG-243), and an index
    anywhere else: a list, a set or a variadic tuple, a node no type describes (an ``Any``, a
    callable's spec), or a union whose branches disagree.

    Dev Notes:
        docs-dev/architecture/cli-parsing/collection-patches.md#the-type-decides-what-a-delete-removes
    """
    index = _list_index(parts[-1])
    if index is None:
        return None
    last = _walk_path(target, parts, union_tag, named=named).layers[-1]
    stands_on = [e.stone.node for e in last if e.after is not None]
    keyed = all(_type_kind(node) in _KEYED_KINDS or _fixed_seq_types(node) is not None for node in stands_on)
    return None if stands_on and keyed else index


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


def _locals_keys_nested(*types: Any, union_tag: str) -> tuple[str, ...]:
    """Names addressing a local-variables namespace at a node *inside* the target, which may be any of *types*.

    A name no class the node may build claims as a real member
    (:func:`_segment_names_real_field`), whatever class its tag names: every variant of a
    union counts, as every subclass of a struct does, and a dict claims every name. Only a
    node that may be struct-like (a struct, a namedtuple, a union holding one) holds a
    namespace. The classes the walk builds for itself (:func:`_synthesized`) build nothing.
    Use :func:`_locals_keys` for the root, where a scalar root also keeps the namespace.

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#every-class-a-node-may-build-counts
    """
    resolved = [_resolve_type(tp) for tp in types]
    members = [m for r in resolved for m in (_union_args_no_none(r) if _is_union(r) else [r]) if not _synthesized(m)]
    if not any(_is_struct(m) or _is_namedtuple(m) for m in members):
        return ()
    return tuple(
        key for key in _defaults.LOCALS_KEYS if not any(_segment_names_real_field(m, key, union_tag) for m in members)
    )


def _step_edges(  # noqa: PLR0913  # the step's own arguments, for every state at once
    states: list[_WalkState],
    part: str,
    depth: int,
    naming: Any,
    union_tag: str,
    *,
    tag_fallback: bool = True,
) -> list[_Edge]:
    """Step every state in *states* along *part* (:func:`_step`), each way it can, in order.

    The one step of every walk: the path walk keeps the edges (:func:`_walk_path`), a walker
    over data the states they land on (:func:`_step_states`).
    """
    return [
        _Edge(state, stone, after)
        for state in states
        for stone, after in _step(state, part, depth, naming, union_tag, tag_fallback=tag_fallback)
    ]


def _distinct(states: Iterable[_WalkState]) -> list[_WalkState]:
    """Return *states* each once, in order, compared by equality: a type need not hash."""
    kept: list[_WalkState] = []
    for state in states:
        if state not in kept:
            kept.append(state)
    return kept


def _landed(edges: list[_Edge]) -> list[_WalkState]:
    """Return the states *edges* land on, each once, in order."""
    return _distinct(e.after for e in edges if e.after is not None)


def _step_states(states: list[_WalkState], part: str, depth: int, naming: Any, union_tag: str) -> list[_WalkState]:
    """Step every state in *states* along *part* (:func:`_step_edges`), keeping each state it lands on once.

    What a walker over data carries from a node to its child: the ways the walk reaches the
    child, each once, so a union met at every level never forks the walk again.
    """
    return _landed(_step_edges(states, part, depth, naming, union_tag))


def _locals_keys_reached(states: list[_WalkState], target: Any, union_tag: str, *, depth: int) -> tuple[str, ...]:
    """Names addressing a namespace at a node the walk reaches in *states*, at *depth* below *target*'s root.

    The one question every consumer (stripping, the declaration scan, the env parser) asks
    at a node, carrying the walk down to it by :func:`_step_states`. The root's are
    :func:`_locals_keys`. Below it, the names no type a state reaches claims
    (:func:`_locals_keys_nested`); none where the node is no position of the target, or where
    a way reaches it below a spec or an untyped token, which holds no namespace.
    """
    if depth == 0:
        return _locals_keys(target, union_tag)
    if not states or any(s.in_spec or s.str_subtree for s in states):
        return ()
    return _locals_keys_nested(*(s.reached for s in states), union_tag=union_tag)


def _locals_segment_index(target: Any, parts: list[str], union_tag: str) -> int | None:
    """Index of the segment at which *parts* enters a namespace, or None.

    Dev Notes:
        docs-dev/architecture/locals.md#per-node-namespaces
    """
    states = [_walk_start(target)]
    for i, part in enumerate(parts):
        if part in _locals_keys_reached(states, target, union_tag, depth=i):
            return i
        states = _step_states(states, part, i, None, union_tag)
    return None


def detect_force_cast(
    path: list[str],
    target: Any,
    union_tag: str,
    named: NamingView | None = None,
) -> tuple[list[str], str | None]:
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
    branch_types = _field_types(target, parent, union_tag, named=named)
    parent_type = _common_type(branch_types)
    if parent_type is None or _segment_names_real_field(parent_type, path[-1], union_tag):
        return path, None
    # Each branch is asked what it holds, never the fold: branches that disagree fold to
    # `str`, which holds no other cast, where the variant construction picks may (BUG-214).
    cast_tp = SCALAR_CAST_TYPES.get(path[-1])
    if cast_tp is not None and not any(holds_the_cast(t, cast_tp) for t in branch_types):
        return path, None
    return parent, path[-1]


def _parse_json_arg(token: str, flag: str, at: Sequence[str | int]) -> Any:
    """Parse token as JSON, raising ConfargError on invalid JSON.

    Args:
        token: The raw CLI token to parse.
        flag: The flag name (e.g. ``--foo``) used in the error message.
        at: The path the value lands at, which it is counted from.

    Returns:
        The decoded JSON value.

    Raises:
        ConfargError: If the token is not valid JSON.
    """
    try:
        return decode_json(token, flag, at)
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
    """Return raw_key with cli_prefix stripped, or raise UnknownArgumentError.

    The bare prefix with a merge suffix (``app+``) is no flag of the namespace, but the
    mistake is about the root, not about the prefix: it strips to the suffix alone, which
    :func:`_merge_suffix_on_root` tells the caller to refuse as such.
    """
    if not cli_prefix:
        return raw_key
    if not _in_cli_prefix(raw_key, cli_prefix):
        if raw_key.startswith(cli_prefix) and _merge_suffix_on_root(suffix := raw_key.removeprefix(cli_prefix)):
            return suffix
        raise UnknownArgumentError.wrong_prefix(token, cli_prefix)
    return "" if raw_key == cli_prefix else raw_key.removeprefix(f"{cli_prefix}.")


def _merge_suffix_on_root(key: str) -> str | None:
    """Return the merge suffix *key* spells on the root, or None: a suffix with no path before it.

    ``--<prefix>+`` strips to that key, as ``<PREFIX>+`` does, and no flag or variable
    patches the root: a struct-like root is patched one field at a time, any other is set
    whole. The CLI refuses it and the environment warns about it, both with the cause.

    Dev Notes:
        docs-dev/architecture/cli-parsing/cli-prefix.md#the-bare-prefix-names-the-root
    """
    return key if key in {APPEND_SUFFIX, DELETE_SUFFIX} else None


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
        ConfargError: When the subpath names no field of the node it descends to, a
            segment spells a key confarg reserves (:func:`_reserved_segment`), or it is
            deeper than a configuration nests.

    Dev Notes:
        docs-dev/architecture/cli-parsing/type-guided-parsing.md#type-guided-parsing
    """
    path = subpath.removesuffix(APPEND_SUFFIX)
    if not path:
        return
    parts = path.split(".")
    refuse_long_path(parts, spelling)
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


def _parse_flag_mode(key: str) -> tuple[list[str], bool, bool]:
    """Decode append/delete mode flags from a flag key.

    Returns ``(path, append_mode, delete_mode)``, the suffix dropped from *path*. Whether a
    delete removes an index or a key is the type's to say (:func:`_delete_index`), and
    force-cast suffixes are *not* decoded here either; see :func:`detect_force_cast`.
    """
    path = key.split(".") if key else []

    append_mode = bool(path) and path[-1].endswith(APPEND_SUFFIX) and len(path[-1]) > 1
    delete_mode = not append_mode and bool(path) and path[-1].endswith(DELETE_SUFFIX) and len(path[-1]) > 1
    if append_mode or delete_mode:
        path[-1] = path[-1][:-1]

    return path, append_mode, delete_mode


@dataclass
class _ParseCtx:
    """Shared parse-loop state threaded through token handlers."""

    argv: Sequence[str]
    target: Any
    union_tag: str
    #: Where ``data`` stands, which reads the identity of each key a flag writes (BUG-244).
    at: MergeAt = field(default_factory=MergeAt)
    #: Where the merge stands at the root of the real target, whose value a non-struct root's flag writes.
    root_at: MergeAt = field(default_factory=MergeAt)
    data: MergeDict = field(default_factory=dict)
    multi_tokens: dict[tuple[str, ...], list[str]] = field(default_factory=dict)
    """Tokens every plain multi-token occurrence contributed, keyed by field path.

    Repeating such a flag is a second spelling of listing its tokens in one go, so the
    accumulated list — not the newest occurrence alone — is what gets shaped into the
    stored value.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    #: What the layers below argv hold: the config files, then the environment.
    below: MergeDict = field(default_factory=dict)
    #: The nodes argv names anywhere (:func:`_argv_named_nodes`): a lower layer's naming types none of them.
    argv_named: frozenset[tuple[str, ...]] = frozenset()
    #: The objects of a root ``--json``, which lie below the flags.
    root_json: list[MergeDict] = field(default_factory=list)

    def write(self, path: list[str], value: Any) -> None:
        """Write *value* at *path*; the empty path is a non-struct root's, whose value ``__root__`` holds.

        A non-struct root's bare flag consumes its value as a field flag of its type does
        (BUG-177), through the same handlers, so the one write they make lands it there.

        Dev Notes:
            docs-dev/architecture/cli-parsing/cli-prefix.md#cli_prefix
        """
        if path:
            _set_nested(self.data, path, value, self.at)
        else:
            _set_nested(self.data, [_defaults.ROOT_KEY], value, self.root_at)

    def naming(self, prefix: tuple[str, ...]) -> Any:
        """Return what the node at *prefix* names for the flag being typed (:data:`NamingView`).

        argv's own naming written so far, else, where argv names neither the node nor an
        ancestor of it, what lies below argv names there: a key written before argv's opener
        is typed by none, and a node argv names, deletes or writes replaces what a lower layer
        named at and below it, as the merge replaces it.

        Dev Notes:
            docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key
        """
        for source in (self.data, *reversed(self.root_json)):
            node = node_at(source, prefix)
            if names_something(node, self.union_tag):
                return node
        if any(prefix[:depth] in self.argv_named for depth in range(len(prefix) + 1)):
            return None
        node = node_at(self.below, prefix)
        return node if names_something(node, self.union_tag) else None


def _handle_delete_token(ctx: _ParseCtx, token: str, path: list[str]) -> None:
    """Apply a delete-mode flag (--foo.1- or --foo.bar-) to data, an index or a key delete (:func:`_delete_index`)."""
    if (unreached := _unreached(ctx.target, path, ctx.union_tag, ctx.naming)) is not None:
        if unreached[0] is _Unreached.NOT_FOUND and _list_index(path[-1]) is not None:
            raise UnknownArgumentError.not_indexable(token, path[:-1])
        _refuse_unreached_flag(token, path, unreached)
    delete_idx = _delete_index(ctx.target, path, ctx.union_tag, ctx.naming)
    if delete_idx is not None:
        parent_path = path[:-1]
        node: Any = ctx.data
        for _p in parent_path:
            node = node[_p] if isinstance(node, dict) and _p in node else {}
        del_key = ListOp.DELETE_AFTER if isinstance(node, dict) and ListOp.APPEND in node else ListOp.DELETE
        _accumulate_list_delete(ctx.data, parent_path, delete_idx, token, delete_key=del_key, at=ctx.at)
    else:
        # A whole-field delete ends the value at this path, so a later multi-token occurrence
        # starts a new list rather than extending the one the delete just discarded. An index
        # delete is a patch *within* the list and leaves the accumulation alone.
        _forget_tokens_below(ctx, path)
        ctx.write(path, DICT_DELETE)


def _collect_append_items(  # the flag's spelling and path name it in a refusal
    args: Sequence[str], i: int, et: Any, spelling: str, at: Sequence[str | int]
) -> tuple[list[Any], int]:
    """Collect append-mode values from args, returning (items, new_i).

    Accepts a JSON array literal as a single token, otherwise consumes space-separated
    tokens until the next flag. A JSON item is data (:func:`~confarg._cast.decode_json`);
    *spelling* names the flag or the variable that refuses a reserved key in one, and *at*
    the path of the list the items are appended to, which an item is counted from.
    """
    if i < len(args) and not _looks_like_flag(args[i]) and args[i].startswith("["):
        try:
            parsed = decode_json(args[i], spelling, at)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return parsed, i + 1

    items: list[Any] = []
    while i < len(args) and not _looks_like_flag(args[i]):
        tok = args[i]
        if tok.startswith("{"):
            try:
                items.append(decode_json(tok, spelling, (*at, len(items))))
            except json.JSONDecodeError:
                items.append(_try_coerce(et, _StrToken(tok), spelling))
        else:
            items.append(_try_coerce(et, _StrToken(tok), spelling))
        i += 1
    return items, i


def _merge_append_ops(existing: Any, append_items: list[Any]) -> MergeDict:
    """Combine append_items with what the path holds, opened as any op below it opens it.

    So an append after a whole value extends that value, and one after a whole-field delete
    extends nothing (:func:`~confarg._merge._open_for_ops`).
    """
    node = _open_for_ops(existing)
    return {**node, ListOp.APPEND: node.get(ListOp.APPEND, []) + append_items}


def _append_element_type(ends: list[Any]) -> Any | None:
    """Return the type an item appended at a path is coerced by, None where nothing there takes an append.

    Asked of each type the walk reaches at the path (:func:`_field_types`), each union spread
    into its variants, never of their fold: a ``+`` appends wherever a branch holds a list, a
    set or a variadic tuple, as ``--xs.<i>`` patches wherever a branch holds a sequence, so
    ``list[int] | None`` and ``list[int] | str`` take ``--xs+`` as a file's ``__append__``
    already did (D4). The items are coerced by the fold of those branches' element types.

    Dev Notes:
        docs-dev/architecture/cli-parsing/collection-patches.md#an-append-reaches-every-sequence-variant
    """
    elements = [_elem_type(node) for end in ends for node in _union_branches(end) if _is_varlen_collection(node)]
    return _common_type(elements)


def _appended_element_type(  # noqa: PLR0913  # the walk, then what the message names
    target: Any,
    path: list[str],
    union_tag: str,
    spelling: str,
    ft: Any,
    *,
    named: NamingView | None = None,
) -> Any:
    """Return the type an item appended at *path* is coerced by, or refuse the append.

    The one check of an append's path, for a flag and a variable alike (FEAT-18). *spelling*
    is the flag or the variable as its channel writes it, and *ft* the field's type, as the
    message names them; what the append reaches is asked of the walk
    (:func:`_append_element_type`).

    Raises:
        ConfargError: If nothing at *path* holds a list, a set or a variadic tuple.
    """
    et = _append_element_type(_field_types(target, path, union_tag, named=named))
    if et is None:
        msg = (
            f"Cannot use + (append) syntax on {spelling!r}:"
            f" field '{'.'.join(path)}' has type {ft!r}, which is not a list, set, or frozenset."
        )
        raise ConfargError(msg)
    return et


def _write_append(data: MergeDict, path: list[str], items: list[Any], at: MergeAt) -> None:
    """Append *items* at *path* of *data*, after whatever the path already holds there, *at* where *data* stands."""
    existing = _peek_nested(data, path, at) if path else None
    _set_nested(data, path, _merge_append_ops(existing, items), at)


def _handle_append_token(
    ctx: _ParseCtx,
    i: int,
    token: str,
    ft: Any,
    path: list[str],
) -> int:
    """Process an append-mode flag (--foo+ items...) and return the new arg index."""
    et = _appended_element_type(ctx.target, path, ctx.union_tag, token, ft, named=ctx.naming)
    append_items, i = _collect_append_items(ctx.argv, i, et, token, path)
    _write_append(ctx.data, path, append_items, ctx.at)
    return i


def _consume_fixed_tuple_args(  # noqa: PLR0913, PLR0917  # token only names the flag in the error
    args: Sequence[str],
    i: int,
    token: str,
    ft: Any,
    path: list[str],
    ctx: _ParseCtx,
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
        items.append(_try_coerce(et, _StrToken(args[i]), token))
        i += 1
    ctx.write(path, items)
    return i


def _union_seq_value(ft: Any, tokens: list[str], token: str, at: Sequence[str | int]) -> Any:
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
    parsed = _lone_json_array(tokens, token, at)
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


def _handle_root_cast(ctx: _ParseCtx, i: int, token: str, *, is_struct: bool, cast_name: str) -> int:
    """Consume the value for a root-level ``--json`` cast. Returns new arg index.

    For a struct/union root the decoded object must be a JSON object; it is collected
    into ``root_json`` and folded in as a base (so per-field CLI flags win) once the
    whole argv is parsed by :func:`~confarg._cast.fold_root_json`.  For a scalar root the
    decoded value is stored under ``__root__``, written in argv order like the bare
    ``--<cli_prefix>`` flag, so of the two the last typed wins: it ends the run the bare
    flag accumulated, as a field's cast ends its flag's.  Invalid JSON raises via
    :func:`resolve_forced_value`.
    """
    args = ctx.argv
    i += 1
    _require_value(args, i, token, "'<json>'")
    value = resolve_forced_value(cast_name, args[i], flag=token)
    if is_struct:
        if not isinstance(value, dict):
            raise ConfargError.root_cast_not_object(token, value)
        ctx.root_json.append(value)
    else:
        ctx.multi_tokens.pop((), None)  # the root's own run; the locals beside it are no part of its value
        ctx.write([], value)
    return i + 1


def _handle_force_cast(  # noqa: PLR0913, PLR0917  # cast_name is a necessary discriminator, not incidental
    args: list[str],
    i: int,
    token: str,
    ctx: _ParseCtx,
    path: list[str],
    cast_name: str,
) -> int:
    """Consume the value for a ``.<cast>`` flag and store the forced value. Returns new arg index.

    Scalar casts store a ``_Pinned`` token; ``.json`` stores the decoded structure and
    raises ``ConfargError`` on invalid JSON (via :func:`resolve_forced_value`). Either replaces
    the value at *path*, so it ends the runs multi-token flags accumulated at or below it.
    """
    _require_value(args, i, token)
    _forget_tokens_below(ctx, path)
    ctx.write(path, resolve_forced_value(cast_name, args[i], flag=token, at=path))
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
    one segment up (BUG-166). Otherwise always raises UnknownArgumentError, for the cause
    :func:`_unreached` gives, which the environment refuses the variable of that path for.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    if _is_dict_at_path(ctx.target, path, ctx.union_tag, ctx.naming):
        if append_mode:
            return _handle_append_token(ctx, i + 1, token, Any, path)
        _require_value(ctx.argv, i + 1, token)
        ctx.write(path, _StrToken(ctx.argv[i + 1]))
        return i + 2
    _refuse_unreached_flag(token, path, _unreached(ctx.target, path, ctx.union_tag, ctx.naming))


def _try_parse_json_list(arg: str, spelling: str, at: Sequence[str | int]) -> list[Any] | None:
    """Parse arg as a JSON array and return it, or None if not valid JSON or not a list.

    The array is data (:func:`~confarg._cast.decode_json`); *spelling* names the flag that
    refuses a reserved key in it, and *at* the path it lands at, which it is counted from.
    """
    try:
        parsed = decode_json(arg, spelling, at)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _lone_json_array(tokens: list[str], spelling: str, at: Sequence[str | int]) -> list[Any] | None:
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
    return _try_parse_json_list(tokens[0], spelling, at)


def _varlen_value(ft: Any, tokens: list[str], spelling: str, at: Sequence[str | int]) -> Any:
    """Shape a varlen collection field's accumulated tokens into its stored value.

    One inline JSON array standing alone is decoded as the whole value; otherwise every
    token becomes an element, coerced eagerly to the element type so the merged dict
    carries the same types whichever channel supplied them.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    parsed = _lone_json_array(tokens, spelling, at)
    if parsed is not None:
        return parsed
    et = _elem_type(ft)
    return [_try_coerce(et, _StrToken(t), spelling) for t in tokens]


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
        and (parsed := _lone_json_array([args[i]], token, path)) is not None
    ):
        ctx.write(path, parsed)
        return i + 1

    # Variable-length collection → consume until the next flag, extending a prior occurrence
    if _is_varlen_collection(ft):
        tokens, i = _consume_multi_tokens(ctx, i, path)
        ctx.write(path, _varlen_value(ft, tokens, token, path))
        return i

    # Fixed-length sequence (tuple[X, Y] or a namedtuple) → consume exact count
    if tt is not None:
        return _consume_fixed_tuple_args(args, i, token, ft, path, ctx)

    # Union with a sequence variant → consume greedily (disambiguation deferred to construct)
    if _union_has_seq_variant(ft):
        tokens, i = _consume_multi_tokens(ctx, i, path)
        ctx.write(path, _union_seq_value(ft, tokens, token, path))
        return i

    # Default: consume one scalar value
    _require_value(args, i, token)
    ctx.write(path, _try_coerce(ft, _StrToken(args[i]), token))
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


def _takes_whole_value(ft: Any | None, value: str) -> bool:
    """Return whether the token *value*, typed after a flag whose field is *ft*, is decoded as a whole ``{...}`` value.

    The one answer for the loop that decodes it and for the scan that reads argv ahead of
    it, the adapters' argument flags (``cli._build._blob_document_from_argv``). A
    ``{``-led value at a field :func:`_accepts_object_value` refuses is text, as the loop
    stores it, so it opens nothing (BUG-216). *ft* is None at a path no branch accepts.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    return not _looks_like_flag(value) and value.startswith("{") and ft is not None and _accepts_object_value(ft)


def _takes_callable_shorthand(ft: Any) -> bool:
    """Return whether a bare string at a field of type *ft* is a callable spec shorthand.

    Mirrors the union handling of :func:`_accepts_object_value`: the union arm answers for
    the optional spellings, so ``Callable[..., T] | None`` reads a bare string the same way
    ``Callable[..., T]`` does.
    """

    def is_callable_variant(v: Any) -> bool:
        return _is_callable(_resolve_type(v))

    return is_callable_variant(ft) or (_is_union(ft) and any(is_callable_variant(v) for v in _union_args_no_none(ft)))


def _open_callable_shorthand(
    data: MergeDict,
    path: list[str],
    target: Any,
    union_tag: str,
    named: NamingView | None = None,
) -> None:
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
        named: What the data the path is typed against names at each node (:func:`_walk_path`).

    Dev Notes:
        docs-dev/architecture/callables.md#cli
    """
    for n in range(1, len(path)):
        if names_an_opener(path[n]):
            continue
        existing = _peek_nested(data, path[:n])
        if not isinstance(existing, str):
            continue
        ft = _resolve_field_type(target, path[:n], union_tag, named=named)
        if ft is not None and _takes_callable_shorthand(_resolve_type(ft)):
            _set_nested(data, path[:n], promote_bare_spec(existing))


def _restart_restated_node(data: MergeDict, path: list[str], target: Any, union_tag: str) -> bool:
    """Empty the node whose opener or tag the value about to be stored at *path* restates.

    A node that already names what it builds (an opener's target, the union tag's class:
    :func:`~confarg.typedload._construct.reads_as_new_value`) and gets a second one starts
    afresh, as it does when a higher layer names one: what it held was written for the first.
    The first opener restates nothing, so the keys written before it stay, in any order; nor
    does an object opener (``class``, ``classfn``) written beside a computation word, which it
    reads as a field, as one dict holding both would. A whole-field delete the node carries
    stays, as it cuts the layers below off either way. The CLI and the environment loop both
    ask it before they store a value. Returns whether it emptied the node, so the CLI loop
    drops the tokens it accumulated below it too.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines
    """
    from confarg._typed_merge import merge_root  # noqa: PLC0415  # import cycle: it walks types with this module

    if not path:
        return False
    at, node = merge_root(target, union_tag), data
    for part in path[:-1]:
        at = at.child(part, node, None)
        node = node.get(part) if isinstance(node, dict) else None
    # A key naming a target ("" stands for whatever is written) restates a node naming one.
    key = path[-1]
    if not isinstance(node, dict) or not at.replaces({key: ""}) or not at.replaces(node):
        return False
    # Among the openers, it restates one that still competes beside it: an object opener
    # takes a computation word as a field, whichever was written first.
    after = _competing_openers({**node, key: ""})
    if names_an_opener(key) and (key not in after or not set(_competing_openers(node)) & set(after)):
        return False
    kept = {ListOp.BASE: DICT_DELETE} if node.get(ListOp.BASE) is DICT_DELETE else {}
    node.clear()
    node.update(kept)
    return True


def _forget_tokens_below(ctx: _ParseCtx, node: list[str]) -> None:
    """Drop the tokens multi-token flags accumulated at or below *node*, which a restart emptied.

    A later occurrence then starts afresh, as one in a higher layer would.
    """
    for key in [k for k in ctx.multi_tokens if list(k[: len(node)]) == node]:
        del ctx.multi_tokens[key]


def _argv_named_nodes(  # noqa: C901  # one lexical scan of argv, per spelling of a naming
    argv: Sequence[str],
    cli_prefix: str,
    config_flag: str,
    union_tag: str,
) -> frozenset[tuple[str, ...]]:
    """Return the path of every node argv names, deletes or writes a value at, read as written.

    A node is named by an opener or a tag flag (``--f.class X``) and by a whole ``{…}`` or
    ``[…]`` value holding one at any depth, a list item by its index; a whole-field delete and
    a bare value written at the node itself (the callable shorthand among them) replace it.
    A lower layer's naming types nothing at or below any of them
    (:meth:`_ParseCtx.naming`). Lexical, so it marks every node a flag writes a value at,
    more than construction reads as named: a lower layer's naming is then only left unused
    below a node argv writes anyway. A flag outside *cli_prefix* is the host's, or refused
    by the loop: it marks nothing. A value is decoded as the loop decodes it
    (:func:`~confarg._cast.decode_json`); one it would refuse marks its node alone, the
    refusal being the loop's (BUG-262).

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key
    """
    words = opener_keys(union_tag)
    found: set[tuple[str, ...]] = set()

    def nested(prefix: tuple[str, ...], value: Any) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                nested((*prefix, str(index)), item)
            return
        if not isinstance(value, dict):
            return
        if names_something(value, union_tag):
            found.add(prefix)
        for k, v in value.items():
            if isinstance(k, str):
                nested((*prefix, k), v)

    i = 0
    while i < len(argv):
        token = argv[i]
        i += 1
        if not _looks_like_flag(token) or not _in_cli_prefix(token[2:], cli_prefix):
            continue
        key = _strip_cli_prefix(token[2:], cli_prefix, token)
        if _addresses_key(key, config_flag):
            continue
        path, append_mode, delete_mode = _parse_flag_mode(key)
        value = argv[i] if i < len(argv) and not _looks_like_flag(argv[i]) else None
        if delete_mode or append_mode:
            if delete_mode:
                found.add(tuple(path))
            continue
        if path and path[-1] in words:
            found.add(tuple(path[:-1]))
            continue
        if value is None:
            continue
        cast = path[-1] if path and path[-1] in FORCE_CAST_NAMES else None
        written = tuple(path[:-1] if cast else path)
        if value.startswith(("{", "[")) or cast == JSON_CAST_NAME:
            try:
                nested(written, decode_json(value, token, written))
            except (json.JSONDecodeError, ConfargError):
                found.add(written)
        else:
            found.add(written)
    return frozenset(found)


def _consume_typed_arg(
    ctx: _ParseCtx,
    i: int,
    token: str,
    ft: Any,
    path: list[str],
) -> int:
    """Consume the value(s) for a resolved, non-append field type and return the new arg index.

    A whole-value flag needs its value: the bare ``--<struct>`` form falls through to the
    missing-value error every other value-taking flag raises. Its value replaces the node,
    so it ends the runs multi-token flags accumulated below it.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    args = ctx.argv
    # JSON object → dataclass / dict / callable / union-with-dc
    if i < len(args) and _takes_whole_value(ft, args[i]):
        _forget_tokens_below(ctx, path)
        ctx.write(path, _parse_json_arg(args[i], token, path))
        return i + 1

    return _consume_collection_or_scalar(ctx, i, token, ft, path)


def _config_pairs_in(
    argv: Sequence[str],
    target: Any,
    cli_prefix: str,
    config_flag: str,
    union_tag: str,
) -> list[tuple[str, str]]:
    """Return the (subpath, mount value) pairs argv's ``--config`` flags name, in argv order, before any value is typed.

    Also cyclopts' pre-parse refusal: cyclopts asserts on a ``nargs="*"`` flag with zero tokens
    before confarg's loop reads argv, so a bare ``--config[.subpath]`` is refused here first.

    The files they mount are part of the config level, which types the flags below a node it
    names, so the pipeline loads them before vanilla's loop runs; the loop reads the same
    pairs as it meets them. A flag outside *cli_prefix* is no confarg flag, and a token that
    is no flag is a value or the host's: neither mounts anything. Each subpath is checked
    against *target*, raising what the loop raises.

    Raises:
        ConfargError: A ``--config[.subpath]`` with no path after it, or a subpath that
            names no node of *target*.
    """
    args = _normalize_eq_args(argv)
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(args):
        token = args[i]
        if not _looks_like_flag(token) or not _in_cli_prefix(token[2:], cli_prefix):
            i += 1
            continue
        key = _strip_cli_prefix(token[2:], cli_prefix, token)
        if not _addresses_key(key, config_flag):
            i += 1
            continue
        _check_mount_subpath(target, _config_subpath(key, config_flag), union_tag, token)
        i, found = _consume_config_paths(args, i, key, config_flag)
        pairs.extend(found)
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
    host_binds_run: Callable[[list[str], Any], bool] | None = None,
    below: MergeDict | None = None,
    observe: Callable[[list[str], Any], None] | None = None,
) -> tuple[MergeDict, list[tuple[str, str]]]:
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
        host_binds_run: Asked of a flag's path and the type it consumed for when the
            token after its run is a value: True when the host bound that token to the
            flag (a framework registering the flag greedily), so it is the stray vanilla
            refuses rather than a positional of the host's.  ``None`` for vanilla,
            whose own loop refuses every stray at the top.
        below: What the layers below argv hold, merged: a node argv names nowhere is
            typed by the class they name there (:meth:`_ParseCtx.naming`).
        observe: Told the path and the type of every value flag as the loop types it,
            in argv order: how registration learns what vanilla's loop consumes.

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
    import_tagged_classes(argv, target, union_tag=union_tag, config_flag=config_flag, below=below)

    # Paths resolve against the locals-grafted target; root classification keeps `target`.
    walk_target = _walk_target(target, _locals_keys(target, union_tag))
    from confarg._typed_merge import merge_root  # noqa: PLC0415  # import cycle: it walks types with this module

    ctx = _ParseCtx(
        argv=argv,
        target=walk_target,
        union_tag=union_tag,
        at=merge_root(walk_target, union_tag),
        root_at=merge_root(target, union_tag),
        below=below or {},
        argv_named=_argv_named_nodes(argv, cli_prefix, config_flag, union_tag),
    )
    config_files: list[tuple[str, str]] = []
    root_json = ctx.root_json  # objects from root `--json`, folded in below fields
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
        if (suffix := _merge_suffix_on_root(key)) is not None:
            raise UnknownArgumentError.merge_suffix_on_the_root(
                token,
                cli_prefix,
                suffix,
                JSON_CAST_NAME,
                deletes=suffix == DELETE_SUFFIX,
                struct=is_struct,
            )

        if _addresses_key(key, config_flag):
            _check_mount_subpath(target, _config_subpath(key, config_flag), union_tag, token)
            i, new_cfgs = _consume_config_paths(argv, i, key, config_flag)
            config_files.extend(new_cfgs)
            continue

        path, append_mode, delete_mode = _parse_flag_mode(key)
        refuse_long_path(path, token, slack=1)  # before the walk types it; its last segment may be a cast

        force_cast: str | None = None
        if not append_mode and not delete_mode:
            path, force_cast = detect_force_cast(path, walk_target, union_tag, ctx.naming)
        refuse_long_path(path, token)

        if host_parsed and not cli_prefix and path and _path_unknown(walk_target, path[:1], union_tag):
            i = _skip_flag_values(argv, i)  # a flag the host registered beside the confarg ones
            continue

        if (reserved := _reserved_segment(path)) is not None:
            raise ConfargError.reserved_key(token, reserved)

        # A bare callable shorthand already stored at a prefix of this path is a spec, not
        # a stale scalar: open it so this flag refines it
        # (docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption).
        _open_callable_shorthand(ctx.data, path, walk_target, union_tag, ctx.naming)

        if delete_mode:
            _handle_delete_token(ctx, token, path)
            i += 1
            continue

        # A second opener or tag at a node names a new target, which the first one's keys
        # are not written for.
        if _restart_restated_node(ctx.data, path, walk_target, union_tag):
            _forget_tokens_below(ctx, path[:-1])

        if force_cast is not None and not path:  # root-level `--json`: inject the whole config
            i = _handle_root_cast(ctx, i, token, is_struct=is_struct, cast_name=force_cast)
            continue

        if is_struct and not path:
            # The bare --<prefix> flag is a scalar root's only CLI spelling; on a
            # struct-like root its value would be written at the empty path, a no-op.
            raise UnknownArgumentError.bare_prefix_on_struct_root(token, cli_prefix)

        if path:
            ft = _resolve_field_type(walk_target, path, union_tag, named=ctx.naming)
            if ft is None:
                i = _handle_unknown_field(ctx, i, token, path, append_mode=append_mode)
                continue
            ft = _resolve_type(ft)
        else:
            # A non-struct root takes what a field flag of its type takes (BUG-177).
            ft = target_r
        i += 1

        if force_cast:
            i = _handle_force_cast(argv, i, token, ctx, path, force_cast)
            continue

        if append_mode:
            i = _handle_append_token(ctx, i, token, ft, path)
            continue

        # A value flag only: a delete, an append and a cast are registered by the argv scans,
        # whose shape no naming changes; a family a naming does change is observed here too.
        if observe is not None and path:
            observe(path, ft)
        i = _consume_typed_arg(ctx, i, token, ft, path)
        if host_binds_run is not None and i < len(argv) and not _looks_like_flag(argv[i]) and host_binds_run(path, ft):
            # The host bound the token after the run to this flag, so it is no positional of
            # the host's: it is the stray vanilla refuses.
            raise UnknownArgumentError.unexpected_positional(argv[i])

    return fold_root_json(ctx.data, root_json, merge_root(target, union_tag)), config_files

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The typed reading of the merge: whether a value replaces what lies below or refines it is the type's to say.

The merge itself stays shape-driven (:mod:`confarg._merge`): at each node it asks a
:class:`~confarg._merge.MergeAt` whether a dict is a value of its own, and what a scalar below
a refining dict means. :class:`TypedAt` answers by the type at that node, as construction will
read the value, and steps into a child by the rules the type walk steps by, reading the spec or
the tag the node holds. Where it cannot type a node it falls back to the shape rule.

Dev Notes:
    docs-dev/architecture/design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, NamedTuple

from confarg import _defaults
from confarg._callable import promote_bare_spec
from confarg._merge import ListOp, MergeAt, MergeDict, _key_spelling
from confarg._naming import UNREADABLE, Named, is_arguments, named_child, named_variant
from confarg._parse_cli import _advance_field_type, _takes_callable_shorthand
from confarg._types import (
    _dict_kv,
    _fixed_position,
    _fixed_seq_types,
    _is_struct_like,
    _resolve_type,
    _StrToken,
    _struct_member_type,
    _union_branches,
    _union_tag_shadowed,
)
from confarg.exceptions import ConfargError
from confarg.typedload._coerce import _coerce_leaf, _type_kind, _TypeKind
from confarg.typedload._construct import reads_as_new_value


def merge_root(target: Any, union_tag: str) -> MergeAt:
    """Return where the merge stands at the root of a configuration of type *target*.

    A struct-like target is the root itself; any other is held under the root key.
    """
    target = _resolve_type(target)
    return TypedAt(target, union_tag) if _is_struct_like(target) else _RootAt(target, union_tag)


def merge_at(tp: Any, union_tag: str) -> MergeAt:
    """Return where the merge stands at a node of type *tp*, the shape rule when *tp* is None."""
    return MergeAt(union_tag) if tp is None else TypedAt(tp, union_tag)


class TypedAt(MergeAt):
    """Where the merge stands at a node of a known type.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines
    """

    __slots__ = ("_reading", "tp")

    union_tag: str

    def __init__(self, tp: Any, union_tag: str) -> None:
        super().__init__(union_tag)
        self.tp = _resolve_type(tp)
        self._reading: _KeyReading | None = None

    def replaces(self, override: MergeDict) -> bool:
        """Return whether construction reads *override* as naming what it builds (:func:`reads_as_new_value`)."""
        return reads_as_new_value(override, self.tp, self.union_tag)

    def opened(self, below: Any) -> Any:
        """Return a bare string a Callable reads as its spec in the dict form a refining dict merges into.

        An expression is opened too: ``{bind: X}`` with no argument is ``X``, whatever ``X``
        resolves to.
        """
        if isinstance(below, str) and _takes_callable_shorthand(self.tp):
            return promote_bare_spec(below)
        return below

    def child(self, key: str | ListOp, below: Any, over: Any) -> MergeAt:
        """Return where the merge stands at *key*, read from the spec or the tag *below* and *over* hold."""
        return _child(self.tp, str(key), _node_view(below, over), self.union_tag)

    def fixed_length(self) -> Any:
        """Return the fixed tuple or namedtuple every branch of the node is, None where they are not one such type."""
        branches = _union_branches(self.tp)
        first = branches[0] if branches else None
        if first is None or any(b != first for b in branches[1:]) or _fixed_seq_types(first) is None:
            return None
        return first

    def key_identity(self, key: Any) -> Any:
        """Return what *key* is to the node's type, so two keys with one identity are one key.

        A dict's key is the key type construction coerces it to, a fixed-length sequence's the
        position it names (:func:`~confarg._types._fixed_position`); a key neither reads, and
        any key of a node whose branches disagree on how to read one, is its spelling
        (:func:`~confarg._merge._key_spelling`).

        Dev Notes:
            docs-dev/architecture/pipeline/deep-merge.md#which-keys-are-one-key
        """
        if isinstance(key, ListOp):
            return key
        if self._reading is None:
            self._reading = _key_reading(self.tp)
        reading = self._reading
        if reading.kind is _KeyKind.KEY:
            try:
                value = _coerce_leaf(reading.tp, _StrToken(key) if isinstance(key, str) else key)
                hash(value)
            except (ConfargError, TypeError, ValueError):
                return _key_spelling(key)
            return (_KeyKind.KEY, value)
        if reading.kind is _KeyKind.POSITION and (position := _fixed_position(reading.tp, key)) is not None:
            return (_KeyKind.POSITION, position)
        return _key_spelling(key)


class _KeyKind(enum.Enum):
    """What a node reads its keys by."""

    KEY = enum.auto()
    POSITION = enum.auto()
    SPELLING = enum.auto()


class _KeyReading(NamedTuple):
    """How a node reads its keys: its kind, and the key type or the fixed-length type it reads them by."""

    kind: _KeyKind
    tp: Any = None


_BY_SPELLING = _KeyReading(_KeyKind.SPELLING)


def _key_reading(tp: Any) -> _KeyReading:
    """Return how a node of type *tp* reads its keys: as every branch reads them, by spelling where they disagree."""
    try:
        readings = [_branch_key_reading(b) for b in _union_branches(tp)]
    except UNREADABLE:
        return _BY_SPELLING
    first = readings[0] if readings else _BY_SPELLING
    return first if all(r == first for r in readings[1:]) else _BY_SPELLING


def _branch_key_reading(tp: Any) -> _KeyReading:
    """Return how one non-union type reads its keys: a dict by a key type, a fixed-length sequence by position."""
    if _type_kind(tp) is _TypeKind.DICT:
        kt = _resolve_type(_dict_kv(tp)[0])
        return _BY_SPELLING if _type_kind(kt) is _TypeKind.ANY else _KeyReading(_KeyKind.KEY, kt)
    if _fixed_seq_types(tp) is not None:
        return _KeyReading(_KeyKind.POSITION, tp)
    return _BY_SPELLING


class _RootAt(MergeAt):
    """Where the merge stands at the root of a target that is no struct, which the root key holds."""

    __slots__ = ("tp",)

    union_tag: str

    def __init__(self, tp: Any, union_tag: str) -> None:
        super().__init__(union_tag)
        self.tp = tp

    def replaces(self, override: MergeDict) -> bool:  # noqa: ARG002  # the root key's holder is no value
        """Return False: the dict holding the root key is no value of the target's."""
        return False

    def child(self, key: str | ListOp, below: Any, over: Any) -> MergeAt:  # noqa: ARG002  # the root key only
        """Return the target's node under the root key, the shape rule elsewhere."""
        return TypedAt(self.tp, self.union_tag) if key == _defaults.ROOT_KEY else MergeAt(self.union_tag)


class _ArgsAt(MergeAt):
    """Where the merge stands at the ``args`` of a target: a mapping typed by the target's parameters."""

    __slots__ = ("params",)

    union_tag: str

    def __init__(self, params: dict[str, Any], union_tag: str) -> None:
        super().__init__(union_tag)
        self.params = params

    def replaces(self, override: MergeDict) -> bool:  # noqa: ARG002  # its keys are parameter names
        """Return False: the mapping's keys are the target's parameters, never an opener."""
        return False

    def child(self, key: str | ListOp, below: Any, over: Any) -> MergeAt:  # noqa: ARG002  # one parameter each
        """Return the node of the parameter *key*, the shape rule for one with no annotation."""
        return merge_at(self.params.get(str(key)), self.union_tag)


def _node_view(below: Any, over: Any) -> MergeDict:
    """The keys of a node that say what it is: *over*'s, and *below*'s where *over* is silent."""
    out: MergeDict = dict(below) if isinstance(below, dict) else {}
    if isinstance(over, dict):
        out.update(over)
    return out


def _child(tp: Any, key: str, node: MergeDict, union_tag: str) -> MergeAt:
    """Return where the merge stands at *key* of a node of type *tp* holding *node*.

    What the node names types the key (:func:`~confarg._naming.named_child`); a node naming
    nothing is typed by *tp* alone.
    """
    answer = named_child(tp, key, node, union_tag)
    if answer is Named.NOTHING:
        return _unnamed_child(tp, key, node, union_tag)
    if isinstance(answer, Named):
        return MergeAt(union_tag)
    if is_arguments(answer):
        return _ArgsAt({f.name: f.type for f in dataclasses.fields(answer)}, union_tag)
    return TypedAt(answer, union_tag)


def _unnamed_child(tp: Any, key: str, node: MergeDict, union_tag: str) -> MergeAt:
    """Return where the merge stands at *key* of a node of type *tp* whose *node* names nothing that types it."""
    match _type_kind(tp):
        case _TypeKind.CALLABLE:
            return MergeAt(union_tag)
        case _TypeKind.ANY:
            return TypedAt(Any, union_tag)
        case _TypeKind.UNION:
            return _union_child(tp, key, node, union_tag)
        case _TypeKind.STRUCT | _TypeKind.TAGGABLE_LEAF:
            # A tag naming no subclass types nothing; no tag, the struct itself.
            if union_tag in node and not _union_tag_shadowed(tp, union_tag):
                return MergeAt(union_tag)
            return _member(tp, key, union_tag)
        case _:
            return merge_at(_advance_field_type(tp, key), union_tag)


def _member(cls: Any, key: str, union_tag: str) -> MergeAt:
    """Return the node of the member *key* of the class *cls*, the shape rule when it names nothing."""
    try:
        return merge_at(_struct_member_type(cls, key), union_tag)
    except UNREADABLE:
        return MergeAt(union_tag)


def _union_child(tp: Any, key: str, node: MergeDict, union_tag: str) -> MergeAt:
    """Return the node at *key* of a union: the named variant's, else what every member knowing *key* agrees on."""
    members = _union_branches(tp)
    if len(members) == 1:
        return _child(members[0], key, node, union_tag)
    variant = named_variant(tp, node, union_tag)
    if variant is not None:
        return _child(variant, key, node, union_tag)
    if union_tag in node and not _union_tag_shadowed(tp, union_tag):
        return MergeAt(union_tag)
    found = [at for m in members if isinstance(at := _child(m, key, node, union_tag), TypedAt)]
    return found[0] if found and all(at.tp == found[0].tp for at in found[1:]) else MergeAt(union_tag)

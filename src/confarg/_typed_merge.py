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

from collections.abc import Callable
from typing import Any

from confarg import _defaults
from confarg._callable import (
    _COMPUTATION_OPENERS,
    _instance_method_owner,
    holds_an_opener,
    promote_bare_spec,
    spec_opener,
    target_parameter_types,
)
from confarg._merge import ListOp, MergeAt, MergeDict
from confarg._parse_cli import _advance_field_type, _takes_callable_shorthand, _union_branches
from confarg._tags import _tag_named_struct
from confarg._types import _is_struct, _is_struct_like, _resolve_type, _struct_member_type, _union_tag_shadowed
from confarg.dictexpr import contains_expression
from confarg.exceptions import ConfargError
from confarg.typedload._coerce import _type_kind, _TypeKind
from confarg.typedload._construct import _is_typed_call, reads_as_new_value

#: What importing a target or a class, or reading its annotations, may raise; the node is then untyped.
_UNREADABLE = (ConfargError, ImportError, ValueError, TypeError, NameError, AttributeError, KeyError)

#: The type of a nested target spec, under ``bind:`` or ``call:``.
_TARGET = Callable[..., Any]


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

    __slots__ = ("tp",)

    union_tag: str

    def __init__(self, tp: Any, union_tag: str) -> None:
        super().__init__(union_tag)
        self.tp = _resolve_type(tp)

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


def _child(tp: Any, key: str, node: MergeDict, union_tag: str) -> MergeAt:  # noqa: PLR0911  # one return per kind
    """Return where the merge stands at *key* of a node of type *tp* holding *node*."""
    if _is_typed_call(node, tp):
        return _spec_child(key, node, _defaults.CALL_KEY, union_tag)
    match _type_kind(tp):
        case _TypeKind.CALLABLE:
            opener = spec_opener(node)
            return MergeAt(union_tag) if opener is None else _spec_child(key, node, opener, union_tag)
        case _TypeKind.ANY:
            if holds_an_opener(node) and (opener := spec_opener(node)) is not None:
                return _spec_child(key, node, opener, union_tag)
            return TypedAt(Any, union_tag)
        case _TypeKind.UNION:
            return _union_child(tp, key, node, union_tag)
        case _TypeKind.STRUCT | _TypeKind.TAGGABLE_LEAF:
            return _member(_tagged_struct(tp, node, union_tag), key, union_tag)
        case _:
            return merge_at(_advance_field_type(tp, key), union_tag)


def _member(cls: Any, key: str, union_tag: str) -> MergeAt:
    """Return the node of the member *key* of the class *cls*, the shape rule when either names nothing."""
    if cls is None:
        return MergeAt(union_tag)
    try:
        return merge_at(_struct_member_type(cls, key), union_tag)
    except _UNREADABLE:
        return MergeAt(union_tag)


def _tagged_struct(tp: Any, node: MergeDict, union_tag: str) -> Any:
    """Return the class a struct node of type *tp* builds: the subclass its tag names, else *tp*.

    A tag a member owns is that member's value; one that names no subclass of *tp* types
    nothing (None).
    """
    if union_tag not in node or _union_tag_shadowed(tp, union_tag):
        return tp
    cls = _class_named(node[union_tag])
    return cls if cls is not None and issubclass(cls, tp) else None


def _class_named(path: Any) -> Any:
    """Return the struct a dotted *path* names, None for an expression or a path naming none."""
    if not isinstance(path, str) or contains_expression(path):
        return None
    return _tag_named_struct(path)


def _union_child(tp: Any, key: str, node: MergeDict, union_tag: str) -> MergeAt:
    """Return the node at *key* of a union: the tagged member's, else what every member knowing *key* agrees on."""
    members = _union_branches(tp)
    if len(members) == 1:
        return _child(members[0], key, node, union_tag)
    if union_tag in node and not _union_tag_shadowed(tp, union_tag):
        cls = _class_named(node[union_tag])
        held = cls is not None and any(_is_struct(m) and issubclass(cls, m) for m in members)
        return _member(cls if held else None, key, union_tag)
    found = [at for m in members if isinstance(at := _child(m, key, node, union_tag), TypedAt)]
    return found[0] if found and all(at.tp == found[0].tp for at in found[1:]) else MergeAt(union_tag)


def _spec_child(key: str, node: MergeDict, opener: str, union_tag: str) -> MergeAt:
    """Return the node at *key* of a spec *opener* opens: a nested target, a target's arguments, or a field."""
    target = node.get(opener)
    if opener in _COMPUTATION_OPENERS:
        return _computation_child(key, target, union_tag)
    if key == opener or not isinstance(target, str) or contains_expression(target):
        return MergeAt(union_tag)
    try:
        cls = _instance_method_owner(target) if opener == _defaults.CLASSFN_KEY else _class_named(target)
    except _UNREADABLE:
        return MergeAt(union_tag)
    return _member(cls, key, union_tag)


def _computation_child(key: str, target: Any, union_tag: str) -> MergeAt:
    """Return the node at *key* of a ``bind:`` or ``call:`` spec over *target*: a nested target, or its arguments."""
    if key in _COMPUTATION_OPENERS:
        return TypedAt(_TARGET, union_tag)
    if key != _defaults.ARGS_KEY or not isinstance(target, str) or contains_expression(target):
        return MergeAt(union_tag)
    try:
        return _ArgsAt(target_parameter_types(target), union_tag)
    except _UNREADABLE:
        return MergeAt(union_tag)

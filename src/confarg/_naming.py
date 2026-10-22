# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What a node names, and the type that gives each key below it.

A node names a class through an opener on a Callable, an ``Any`` or a typed call, or through
the union tag on a struct, a taggable leaf or a union. Construction builds the keys below it
as that class reads them, so the type walk of a path (:mod:`confarg._parse_cli`) and the
typed merge (:mod:`confarg._typed_merge`) both ask :func:`named_variant` and
:func:`named_child` what a key is, and cannot drift from construction or from each other.

Dev Notes:
    docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#a-node-types-its-keys-by-the-class-it-names
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence

    from confarg._merge import MergeAt, MergeDict

from confarg import _defaults
from confarg._callable import (
    _COMPUTATION_OPENERS,
    _OPENERS,
    _fillable_params,
    _instance_method_owner,
    _target_signature,
    holds_an_opener,
    spec_opener,
    target_parameter_types,
    yielded_callable_path,
)
from confarg._import import _import_dotted
from confarg._merge import _deep_merge, _peek_nested
from confarg._tags import class_named
from confarg._types import (
    _class_of,
    _is_struct,
    _resolve_type,
    _struct_member_names,
    _struct_member_type,
    _tagged_struct,
    _union_branches,
    _union_tag_shadowed,
)
from confarg.dictexpr import contains_expression
from confarg.dictexpr._expressions import _list_index
from confarg.exceptions import ConfargError
from confarg.typedload._coerce import _type_kind, _TypeKind
from confarg.typedload._construct import _first_spec_reader, _is_typed_call, spec_reading_variant


class Named(enum.Enum):
    """An answer of :func:`named_child` that is no type."""

    #: The node names nothing that types its keys: the type alone answers.
    NOTHING = enum.auto()
    #: The node names something, but not a class whose reading of the key is known: the key is untyped.
    UNTYPED = enum.auto()
    #: The node names a class that declares no such key.
    REFUSED = enum.auto()


#: The type of a nested target spec, under ``bind:`` or ``call:``.
TARGET = Callable[..., Any]

#: Set on the class :func:`arguments_of` builds: the arguments of a target, which no walk reads as a struct's.
ARGUMENTS = "__confarg_arguments__"

#: Set on the class :func:`arguments_of` builds: the names its target takes with no annotation, or by ``**kwargs``.
UNTYPED_ARGUMENTS = "__confarg_untyped_arguments__"

#: Set on the class :func:`arguments_of` builds when its target takes ``**kwargs``: any name is one of its arguments.
ANY_ARGUMENT = "__confarg_any_argument__"

#: What reading a class's members, a signature or its annotations may raise; the key is then untyped.
#: An import, which runs a module's top level, is read by :func:`~confarg._tags.class_named` instead.
UNREADABLE = (ConfargError, ImportError, ValueError, TypeError, NameError, AttributeError, KeyError)


class _Reading(NamedTuple):
    """What a node names: the key naming it, and how its other keys read."""

    #: The opener or the union tag naming the node; its value is a dotted-path leaf, or a target spec.
    key: str
    #: The class whose members the node's other keys are; None for a computation, or a class no import reads.
    cls: type | None
    #: A ``bind:`` or ``call:``, whose other keys are a nested target and the target's ``args``.
    computation: bool = False


def _reading(tp: Any, node: Any, union_tag: str) -> _Reading | None:  # noqa: PLR0911  # one return per kind
    """Return what the node of the non-union type *tp* holding *node* names, None when it names nothing.

    The one reading of a node :func:`named_child` types a key by and :func:`named_member_names`
    lists the keys of: a typed call, an opener on a Callable or an ``Any``, the union tag on a
    struct or a taggable leaf naming a subclass of it.
    """
    if not isinstance(node, dict):
        return None
    if _is_typed_call(node, tp):
        return _Reading(_defaults.CALL_KEY, None, computation=True)
    match _type_kind(tp):
        case _TypeKind.CALLABLE | _TypeKind.ANY:
            opener = spec_opener(node) if holds_an_opener(node) else None
            if opener is None:
                return None
            if opener in _COMPUTATION_OPENERS:
                return _Reading(opener, None, computation=True)
            return _Reading(opener, _object_class(opener, node.get(opener)))
        case _TypeKind.STRUCT | _TypeKind.TAGGABLE_LEAF:
            if union_tag not in node or _union_tag_shadowed(tp, union_tag):
                return None
            cls = class_named(node[union_tag])
            bound = _tagged_struct(cls, tp) if cls is not None and _is_struct(cls) else None
            return None if bound is None else _Reading(union_tag, bound)
        case _:
            return None


def _object_class(opener: str, target: Any) -> type | None:
    """Return the class whose fields an object opener's spec holds: the class ``class:`` names, ``classfn:``'s owner."""
    if opener != _defaults.CLASSFN_KEY:
        return class_named(target)
    if not isinstance(target, str) or contains_expression(target):
        return None
    try:
        return _instance_method_owner(target)
    except Exception:  # noqa: BLE001  # the owner's module top level may raise anything; construction reports it
        return None


def names_something(node: Any, union_tag: str) -> bool:
    """Return whether the dict *node* holds a key that may name what it builds: an opener or the union tag."""
    return isinstance(node, dict) and (union_tag in node or holds_an_opener(node))


def named_variant(tp: Any, node: MergeDict, union_tag: str) -> Any:
    """Return the variant of the union *tp* that builds the dict *node*, None when *node* names none.

    The variant a tag names (a struct variant the class subclasses, else the variant that reads
    specs, as :func:`~confarg.typedload._construct._construct_union_by_tag` builds it), or the one
    that reads an opener *node* holds (:func:`~confarg.typedload._construct.spec_reading_variant`).
    A ``call:`` is the union's, no variant's. *tp* that is no union of several variants names none.
    """
    members = _union_branches(tp)
    if len(members) < 2 or not isinstance(node, dict):  # noqa: PLR2004  # a union of several variants
        return None
    if union_tag in node and not _union_tag_shadowed(tp, union_tag):
        cls = class_named(node[union_tag])
        if cls is None:
            return None
        matching = [m for m in members if _is_struct(m) and _tagged_struct(cls, m) is not None]
        if len({_class_of(m) for m in matching}) == 1:
            # One variant, or one generic parameterized apiece: the first binding types the keys,
            # as construction tries it first.
            return matching[0]
        return None if matching else _first_spec_reader(members)
    if _is_typed_call(node, tp):
        return None
    return spec_reading_variant(tp, node, union_tag)


def named_child(tp: Any, key: str, node: MergeDict, union_tag: str) -> Any:  # one return per kind
    """Return the type of *key* below a node of the non-union type *tp* holding *node*, or a :class:`Named`.

    The node names a class by an opener on a Callable, an ``Any`` or a typed call, or by the
    union tag on a struct or a taggable leaf, and *key* is what that class reads it as: a
    field of the class an object opener or a tag names, a nested target below ``bind:`` or
    ``call:``, the arguments of the target under ``args``. The value of a tag or an object
    opener is a dotted path, so it is a ``str`` leaf.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#a-node-types-its-keys-by-the-class-it-names
    """
    reading = _reading(tp, node, union_tag)
    if reading is None:
        return Named.NOTHING
    if reading.computation:
        return _computation_child(key, node.get(reading.key))
    if key == reading.key:
        return str
    return Named.UNTYPED if reading.cls is None else _member(reading.cls, key)


def _computation_child(key: str, target: Any) -> Any:
    """Return the type of *key* in a ``bind:`` or ``call:`` spec over *target*: a nested target, or its arguments."""
    if key in _COMPUTATION_OPENERS:
        return TARGET
    if key != _defaults.ARGS_KEY:
        return Named.REFUSED
    path = yielded_callable_path(target) if isinstance(target, dict) else target
    return Named.UNTYPED if path is None else arguments_of(path)


def _member(cls: type, key: str) -> Any:
    """Return the type the class *cls* builds its member *key* as, :attr:`Named.REFUSED` when it declares none."""
    try:
        tp = _struct_member_type(cls, key)
    except UNREADABLE:
        return Named.UNTYPED
    return Named.REFUSED if tp is None else tp


def arguments_of(path: Any) -> Any:
    """Return a class whose fields are the parameters the target *path* takes, :attr:`Named.UNTYPED` when unreadable.

    A field per parameter construction fills one argument each, typed by its annotation; one with
    none is listed in :data:`UNTYPED_ARGUMENTS`, and :data:`ANY_ARGUMENT` says the target takes
    ``**kwargs``. The class stands for the mapping under ``args`` in the type walk only; nothing
    builds it.
    """
    if not isinstance(path, str) or contains_expression(path):
        return Named.UNTYPED
    try:
        obj = _import_dotted(path)
    except Exception:  # noqa: BLE001  # the target's module top level may raise anything; construction reports it
        return Named.UNTYPED
    try:
        return _arguments_class(path, obj)
    except UNREADABLE:
        return Named.UNTYPED


@functools.lru_cache(maxsize=256)
def _arguments_class(path: str, obj: Any) -> type:
    """Build :func:`arguments_of`'s class for the target *path*, which imports as *obj*: one per target."""
    del obj  # the cache key: a path re-bound to another object is another class
    params = _target_signature(path).parameters
    hints = target_parameter_types(path)
    fillable = _fillable_params(params)
    fields = [(p.name, hints[p.name], dataclasses.field(default=None)) for p in fillable if p.name in hints]
    untyped = frozenset(p.name for p in fillable if p.name not in hints)
    any_name = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    namespace = {ARGUMENTS: True, UNTYPED_ARGUMENTS: untyped, ANY_ARGUMENT: any_name}
    return dataclasses.make_dataclass("_Arguments", fields, namespace=namespace)


def is_arguments(tp: Any) -> bool:
    """Return whether *tp* is a class :func:`arguments_of` built."""
    return bool(getattr(_resolve_type(tp), ARGUMENTS, False))


def takes_untyped_argument(tp: Any, key: str) -> bool:
    """Return whether the arguments class *tp* takes *key* untyped: unannotated, or by ``**kwargs``."""
    return is_arguments(tp) and (key in getattr(tp, UNTYPED_ARGUMENTS) or getattr(tp, ANY_ARGUMENT))


@functools.cache
def opener_keys(union_tag: str) -> frozenset[str]:
    """Return the keys that may name what a node builds: the openers and the union tag."""
    return frozenset((*_OPENERS, union_tag))


def node_at(data: Any, prefix: Sequence[str]) -> Any:
    """Return the node at *prefix* in *data*, stepping a dict by its key and a list by an index; None where absent.

    An index is a segment as ``str()`` writes one (:func:`~confarg.dictexpr._expressions._list_index`),
    so a naming inside a list is read where a flag or a variable addresses it (``fs.0``).
    """
    node = data
    for part in prefix:
        if isinstance(node, dict):
            node = _peek_nested(node, [part])
        elif isinstance(node, list) and (index := _list_index(part)) is not None and -len(node) <= index < len(node):
            node = node[index]
        else:
            return None
    return node


class MergedNaming:
    """The naming view of a layer merged over what lies below it, as the merge merges them.

    A naming the layer holds at a node or an ancestor replaces what lies below there, and its
    delete drops it (:func:`~confarg._merge._deep_merge`, typed by *at*), so a lower layer's
    naming types only what the layer leaves standing. The layer may grow while it is read:
    :meth:`changed` merges it again at the next look-up.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key
    """

    __slots__ = ("_at", "_below", "_layer", "_merged", "_union_tag")

    def __init__(self, below: MergeDict, layer: MergeDict, at: MergeAt, union_tag: str) -> None:
        self._below, self._layer, self._at, self._union_tag = below, layer, at, union_tag
        self._merged: MergeDict | None = None

    def changed(self) -> None:
        """Merge the layer again at the next look-up: it was written to."""
        self._merged = None

    def __call__(self, prefix: tuple[str, ...]) -> Any:
        """Return what the node at *prefix* names in the merged layers, None where it names nothing."""
        if self._merged is None:
            self._merged = _deep_merge(self._below, self._layer, at=self._at)
        node = node_at(self._merged, prefix)
        return node if names_something(node, self._union_tag) else None


def named_member_names(tp: Any, node: MergeDict, union_tag: str) -> list[str]:
    """Return the names the class a node of type *tp* holding *node* names reads as its keys, [] for none.

    The listing view of :func:`named_child`, for the environment, which matches a segment's
    spelling against the names rather than looks one up.
    """
    if not isinstance(node, dict):
        return []
    variant = named_variant(tp, node, union_tag)
    if variant is None and len(_union_branches(tp)) > 1:  # a union naming no variant
        return []
    reading = _reading(_union_branches(variant if variant is not None else tp)[0], node, union_tag)
    if reading is None or reading.cls is None or not _is_struct(reading.cls):
        return []
    try:
        return _struct_member_names(reading.cls)
    except UNREADABLE:
        return []

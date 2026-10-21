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

import contextlib
import dataclasses
import enum
import functools
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from confarg._merge import MergeDict

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
from confarg._merge import _peek_nested
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

#: What importing a class or reading a signature may raise at parse; the key is then untyped.
_UNREADABLE = (Exception,)


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
        cls = _class_named(node[union_tag])
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


def named_child(tp: Any, key: str, node: MergeDict, union_tag: str) -> Any:  # noqa: PLR0911  # one return per kind
    """Return the type of *key* below a node of the non-union type *tp* holding *node*, or a :class:`Named`.

    The node names a class by an opener on a Callable, an ``Any`` or a typed call, or by the
    union tag on a struct or a taggable leaf, and *key* is what that class reads it as: a
    field of the class an object opener or a tag names, a nested target below ``bind:`` or
    ``call:``, the arguments of the target under ``args``. The value of a tag or an object
    opener is a dotted path, so it is a ``str`` leaf.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#a-node-types-its-keys-by-the-class-it-names
    """
    if not isinstance(node, dict):
        return Named.NOTHING
    if _is_typed_call(node, tp):
        return _spec_child(key, node, _defaults.CALL_KEY)
    match _type_kind(tp):
        case _TypeKind.CALLABLE | _TypeKind.ANY:
            opener = spec_opener(node) if holds_an_opener(node) else None
            return Named.NOTHING if opener is None else _spec_child(key, node, opener)
        case _TypeKind.STRUCT | _TypeKind.TAGGABLE_LEAF:
            if union_tag not in node or _union_tag_shadowed(tp, union_tag):
                return Named.NOTHING
            if key == union_tag:
                return str
            cls = _class_named(node[union_tag])
            bound = _tagged_struct(cls, tp) if cls is not None and _is_struct(cls) else None
            if bound is None:
                return Named.NOTHING
            return _member(bound, key)
        case _:
            return Named.NOTHING


def _spec_child(key: str, node: MergeDict, opener: str) -> Any:  # noqa: PLR0911  # one return per kind
    """Return the type of *key* in a spec *opener* opens: a nested target, a target's arguments, or a field."""
    target = node.get(opener)
    if opener in _COMPUTATION_OPENERS:
        if key in _COMPUTATION_OPENERS:
            return TARGET
        if key != _defaults.ARGS_KEY:
            return Named.REFUSED
        path = yielded_callable_path(target) if isinstance(target, dict) else target
        return Named.UNTYPED if path is None else arguments_of(path)
    if key == opener:
        return str
    if not isinstance(target, str) or contains_expression(target):
        return Named.UNTYPED
    try:
        cls = _instance_method_owner(target) if opener == _defaults.CLASSFN_KEY else _import_dotted(target)
    except _UNREADABLE:
        return Named.UNTYPED
    if not isinstance(cls, type):
        return Named.UNTYPED
    return _member(cls, key)


def _member(cls: type, key: str) -> Any:
    """Return the type the class *cls* builds its member *key* as, :attr:`Named.REFUSED` when it declares none."""
    try:
        tp = _struct_member_type(cls, key)
    except _UNREADABLE:
        return Named.UNTYPED
    return Named.REFUSED if tp is None else tp


def _class_named(path: Any) -> type | None:
    """Return the class a dotted *path* names, None for an expression, a path naming none, or a failed import."""
    if not isinstance(path, str) or contains_expression(path):
        return None
    try:
        cls = _import_dotted(path)
    except _UNREADABLE:
        return None
    return cls if isinstance(cls, type) else None


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
        return _arguments_class(path, obj)
    except _UNREADABLE:
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
    namespace: Mapping[str, Any] = {ARGUMENTS: True, UNTYPED_ARGUMENTS: untyped, ANY_ARGUMENT: any_name}
    return dataclasses.make_dataclass("_Arguments", fields, namespace=dict(namespace))


def is_arguments(tp: Any) -> bool:
    """Return whether *tp* is a class :func:`arguments_of` built."""
    return bool(getattr(_resolve_type(tp), ARGUMENTS, False))


def takes_untyped_argument(tp: Any, key: str) -> bool:
    """Return whether the arguments class *tp* takes *key* untyped: unannotated, or by ``**kwargs``."""
    return is_arguments(tp) and (key in getattr(tp, UNTYPED_ARGUMENTS) or getattr(tp, ANY_ARGUMENT))


def opener_keys(union_tag: str) -> frozenset[str]:
    """Return the keys that may name what a node builds: the openers and the union tag."""
    return frozenset((*_OPENERS, union_tag))


def layered_naming(*layers: MergeDict, union_tag: str) -> Callable[[tuple[str, ...]], Any]:
    """Return the naming view of *layers*, highest first: at each node, the first layer that names it.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key
    """

    def naming(prefix: tuple[str, ...]) -> Any:
        for layer in layers:
            node = _peek_nested(layer, list(prefix))
            if names_something(node, union_tag):
                return node
        return None

    return naming


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
    tp = _union_branches(variant if variant is not None else tp)[0]
    cls: Any = None
    if _type_kind(tp) in (_TypeKind.STRUCT, _TypeKind.TAGGABLE_LEAF) and union_tag in node:
        cls = _class_named(node[union_tag])
    elif _type_kind(tp) in (_TypeKind.CALLABLE, _TypeKind.ANY) and holds_an_opener(node):
        opener = spec_opener(node)
        target = node.get(opener) if opener is not None else None
        if opener == _defaults.CLASS_KEY:
            cls = _class_named(target)
        elif opener == _defaults.CLASSFN_KEY and isinstance(target, str) and not contains_expression(target):
            with contextlib.suppress(*_UNREADABLE):
                cls = _instance_method_owner(target)
    if cls is None or not _is_struct(cls):
        return []
    try:
        return _struct_member_names(cls)
    except _UNREADABLE:
        return []

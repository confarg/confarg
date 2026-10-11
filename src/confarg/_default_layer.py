# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lay a target's field defaults under a merged dict, as the base layer every source patches.

``build()``, ``resolve()`` and ``from_dict()`` lay the defaults a class declares as values
below the data they are given, through the merge's own combiner, so a pending list op or
index patch applies over a default as it would over a lower file holding it, and an
expression reads a default nobody set. A default nobody touched is recorded and taken out
again once expressions are resolved: construction applies it, as it always did.

Dev Notes:
    docs-dev/architecture/design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer
"""

from __future__ import annotations

import dataclasses
import enum
from typing import TYPE_CHECKING, Any, NamedTuple

from confarg import _defaults
from confarg._merge import ListOp, _is_pin_dict, _merge_existing_value
from confarg._tags import _tag_named_struct
from confarg._types import (
    _all_have_defaults,
    _dict_kv,
    _elem_type,
    _is_seq_variant,
    _is_struct,
    _is_struct_like,
    _namedtuple_fields,
    _resolve_type,
    _struct_declared_defaults,
    _struct_fields,
    _struct_required,
    _tuple_types,
    _union_args_no_none,
    _union_has_seq_variant,
    _union_tag_shadowed,
)
from confarg.dictexpr import contains_expression, escape_expressions
from confarg.exceptions import _spell_field_path
from confarg.typedload._coerce import _LEAF_COERCIONS, _is_struct_variant, _type_kind, _TypeKind
from confarg.typedload._construct import _is_typed_call

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from confarg._merge import MergeDict

#: A position in the data, one segment per step: a dict key (a pending op's marker included)
#: or a list index.
DataPath = tuple["str | int | ListOp", ...]

# A default that is not laid: anything but a leaf value, a tuple of them, or None.
_NOT_LAID: Any = object()

# What reading a class's fields or defaults may raise; such a class is left to construction.
_INTROSPECTION_ERRORS = (ValueError, TypeError, NameError, AttributeError)

_SEQUENCE_KINDS = frozenset(
    {_TypeKind.LIST, _TypeKind.SET, _TypeKind.FROZENSET, _TypeKind.TUPLE, _TypeKind.NAMEDTUPLE},
)


class LaidDefaults(NamedTuple):
    """The data with the defaults laid under it, and where it holds a default nobody touched."""

    data: MergeDict
    untouched: tuple[DataPath, ...]


@dataclasses.dataclass
class _Walk:
    """What one laying walk carries: the tag spelling, its mode, and the untouched paths it records."""

    union_tag: str
    for_resolution: bool
    untouched: list[DataPath] = dataclasses.field(default_factory=list)


def lay_defaults(target: Any, data: MergeDict, union_tag: str, *, for_resolution: bool) -> LaidDefaults:
    """Lay *target*'s field defaults under *data*, never mutating it.

    A field the data holds is combined with its default where the default is a list base
    and the data a patch over it (:func:`~confarg._merge._merge_existing_value`); with
    *for_resolution*, a field the data omits gets its default, recorded as untouched, so
    an expression can read it, and a default string is laid escaped, so resolution gives
    the class's text back. Without it (``from_dict()``, which resolves nothing), only the
    patches are combined.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer
    """
    walk = _Walk(union_tag, for_resolution)
    target = _resolve_type(target)
    if _is_struct_like(target):
        laid = _node(target, data, (), walk)
    elif _defaults.ROOT_KEY in data:
        root = _node(target, data[_defaults.ROOT_KEY], (_defaults.ROOT_KEY,), walk)
        laid = data if root is data[_defaults.ROOT_KEY] else {**data, _defaults.ROOT_KEY: root}
    else:
        laid = data
    return LaidDefaults(laid, tuple(walk.untouched))


def drop_untouched(data: MergeDict, untouched: Sequence[DataPath]) -> MergeDict:
    """Return *data* without the untouched defaults :func:`lay_defaults` recorded, never mutating it.

    Resolution rewrites only expression strings, so every recorded path still leads where
    it did. Construction applies those defaults itself, as the class's own objects.
    """
    for path in untouched:
        data = _without(data, path)
    return data


def _without(node: Any, path: DataPath) -> Any:
    """Return *node* without what *path* reaches, copying only the containers along it."""
    head, *rest = path
    if isinstance(node, dict):
        if head not in node:
            return node
        if not rest:
            return {k: v for k, v in node.items() if k != head}
        return {**node, head: _without(node[head], tuple(rest))}
    if isinstance(node, list) and isinstance(head, int) and 0 <= head < len(node) and rest:
        copy = list(node)
        copy[head] = _without(node[head], tuple(rest))
        return copy
    return node


def _spelled(path: DataPath) -> str:
    """Spell a data path as a message names it: the root key and the pending ops left out."""
    segments = [s for s in path if not isinstance(s, ListOp)]
    if segments[:1] == [_defaults.ROOT_KEY]:
        segments = segments[1:]
    return _spell_field_path(tuple(str(s) if not isinstance(s, int) else s for s in segments))


def _node(tp: Any, node: Any, path: DataPath, walk: _Walk) -> Any:
    """Lay the defaults below *node*, which the data holds where the type is *tp*."""
    tp = _resolve_type(tp)
    if not isinstance(node, dict | list) or _is_pin_dict(node) or _is_typed_call(node, tp):
        return node
    kind = _type_kind(tp)
    if kind is _TypeKind.STRUCT:
        cls = _struct_built_from(tp, node, walk.union_tag) if isinstance(node, dict) else None
        return node if cls is None else _struct(cls, node, path, walk)
    if kind is _TypeKind.UNION:
        return _union(tp, node, path, walk)
    if kind in _SEQUENCE_KINDS:
        return _sequence(tp, node, path, walk)
    if kind is _TypeKind.DICT and isinstance(node, dict):
        _, vt = _dict_kv(tp)
        return _copied_if_changed(
            node, {k: v if isinstance(k, ListOp) else _node(vt, v, (*path, k), walk) for k, v in node.items()}
        )
    return node


def _tagged_class(tag: Any) -> Any:
    """The struct a tag names, None for a tag that is an expression or names none."""
    if not isinstance(tag, str) or contains_expression(tag):
        return None
    return _tag_named_struct(tag)


def _struct_built_from(tp: Any, node: MergeDict, union_tag: str) -> Any:
    """Return the class construction builds *node* as at a field of struct type *tp*, None if unsure.

    Mirrors ``_construct_struct_dispatch``: an unshadowed tag names the class, a tag the
    struct's own field owns is data, and with no tag a struct that has subclasses is refused,
    so nothing is laid below a node construction would not build as one class.
    """
    try:
        if union_tag in node:
            if not _union_tag_shadowed(tp, union_tag):
                cls = _tagged_class(node[union_tag])
                return cls if cls is not None and issubclass(cls, tp) else None
            return tp if union_tag in _struct_fields(tp) else None
        return None if any(_is_struct(s) for s in tp.__subclasses__()) else tp
    except _INTROSPECTION_ERRORS:
        return None


def _union(tp: Any, node: Any, path: DataPath, walk: _Walk) -> Any:
    """Lay defaults below a union-typed node where one variant is certain: the only one, or the tagged one."""
    variants = [_resolve_type(v) for v in _union_args_no_none(tp)]
    if len(variants) == 1:
        return _node(variants[0], node, path, walk)
    if not isinstance(node, dict) or walk.union_tag not in node or _union_tag_shadowed(tp, walk.union_tag):
        return node
    cls = _tagged_class(node[walk.union_tag])
    matching = [v for v in variants if cls is not None and _is_struct(v) and issubclass(cls, v)]
    return _struct(cls, node, path, walk) if len(matching) == 1 else node


def _struct(cls: Any, node: MergeDict, path: DataPath, walk: _Walk) -> MergeDict:
    """Lay the defaults *cls* declares at its fields under *node*."""
    try:
        fields = _struct_fields(cls)
        defaults = _struct_declared_defaults(cls)
        required = _struct_required(cls)
    except _INTROSPECTION_ERRORS:
        return node
    out = dict(node)
    for name, ft in fields.items():
        fpath = (*path, name)
        laid = _merged_form(defaults[name], ft, walk) if name in defaults else _NOT_LAID
        if name in node:
            value = node[name]
            if isinstance(laid, list) and _patches_a_list(value, ft, walk.union_tag):
                value = _merge_existing_value(laid, value, _spelled(fpath), walk.union_tag)
            out[name] = _node(ft, value, fpath, walk)
        elif not walk.for_resolution:
            continue
        elif laid is not _NOT_LAID:
            out[name] = laid
            walk.untouched.append(fpath)
        elif name in required and _is_struct_variant(ft) and _all_have_defaults(ft):
            # Construction builds such a field from {} (``_construct_struct``): its class's
            # defaults are what it will hold.
            out[name] = _struct(_resolve_type(ft), {}, fpath, _Walk(walk.union_tag, for_resolution=True))
            walk.untouched.append(fpath)
    return _copied_if_changed(node, out)


def _patches_a_list(value: Any, ft: Any, union_tag: str) -> bool:
    """Whether *value*, at a field of type *ft*, is a patch the field's list default is the base of.

    A dict carrying its own base, a tag, a cast pin or a typed call replaces what lies
    below rather than patching it, so the default is not laid under it.
    """
    return (
        isinstance(value, dict)
        and (_is_seq_variant(ft) or _union_has_seq_variant(ft))
        and ListOp.BASE not in value
        and union_tag not in value
        and not _is_pin_dict(value)
        and not _is_typed_call(value, ft)
    )


def _sequence(tp: Any, node: Any, path: DataPath, walk: _Walk) -> Any:
    """Lay defaults below each element a sequence node holds: a list's items, a patch's values."""
    element = _element_type(tp)
    if isinstance(node, list):
        return _items(node, element, path, walk)
    out = dict(node)
    base = node.get(ListOp.BASE)
    if isinstance(base, list):
        out[ListOp.BASE] = _items(base, element, (*path, ListOp.BASE), walk)
    appended = node.get(ListOp.APPEND)
    if isinstance(appended, list):
        out[ListOp.APPEND] = _items(appended, lambda _: element(None), (*path, ListOp.APPEND), walk)
    elif isinstance(appended, dict):
        out[ListOp.APPEND] = _node(element(None), appended, (*path, ListOp.APPEND), walk)
    if not isinstance(base, list):
        # Beside a base, an index value refines the element it reaches, which holds its own.
        for k, v in node.items():
            if not isinstance(k, ListOp):
                out[k] = _node(element(_index(k)), v, (*path, k), walk)
    return _copied_if_changed(node, out)


def _items(items: list[Any], element: Callable[[Any], Any], path: DataPath, walk: _Walk) -> list[Any]:
    """Lay defaults below each item of *items*, typed by its position."""
    return _copied_if_changed(items, [_node(element(i), v, (*path, i), walk) for i, v in enumerate(items)])


def _element_type(tp: Any) -> Callable[[Any], Any]:
    """Return what a sequence of type *tp* holds at a position, a namedtuple's field name included."""
    if _type_kind(tp) is _TypeKind.NAMEDTUPLE:
        fields = _namedtuple_fields(tp)
        names, positions = list(fields), list(fields.values())
    else:
        names, positions = [], (_tuple_types(tp) if _type_kind(tp) is _TypeKind.TUPLE else None)

    def element(i: Any) -> Any:
        if positions is None:
            return _elem_type(tp)
        if isinstance(i, int) and -len(positions) <= i < len(positions):
            return positions[i]
        return positions[names.index(i)] if i in names else Any

    return element


def _index(key: Any) -> Any:
    """The position an index key spells, or the key itself (a namedtuple's field name)."""
    try:
        return int(key)
    except (TypeError, ValueError):
        return key


def _copied_if_changed(original: Any, rebuilt: Any) -> Any:
    """Return *original* when *rebuilt* holds the very same values, so an untouched node stays shared."""
    if isinstance(original, dict):
        same = original.keys() == rebuilt.keys() and all(rebuilt[k] is v for k, v in original.items())
    else:
        same = len(original) == len(rebuilt) and all(a is b for a, b in zip(original, rebuilt, strict=True))
    return original if same else rebuilt


def _merged_form(value: Any, ft: Any, walk: _Walk) -> Any:
    """Return a default as the merged dict holds such a value, or ``_NOT_LAID`` when it is not laid.

    Only what the class declares as a value is laid (tier 1): a leaf, ``None``, or a tuple
    of them at a sequence-typed field, as the positional list a file would write. A list, a
    dict, a set and a struct instance are not.
    """
    if isinstance(value, list | dict | set | frozenset):
        return _NOT_LAID
    if isinstance(value, tuple) and not (_is_seq_variant(ft) or _union_has_seq_variant(ft)):
        return _NOT_LAID
    return _element_form(value, walk)


def _element_form(value: Any, walk: _Walk) -> Any:
    """Return a leaf, or a tuple's element, in its merged form; ``_NOT_LAID`` for anything else."""
    if isinstance(value, enum.Enum):
        return value
    if isinstance(value, str):
        return escape_expressions(value) if walk.for_resolution else value
    if value is None or isinstance(value, (bool, int, float, *_LEAF_COERCIONS)):
        return value
    if isinstance(value, tuple | list):
        items = [_element_form(v, walk) for v in value]
        return _NOT_LAID if any(i is _NOT_LAID for i in items) else items
    if isinstance(value, dict):
        entries = {k: _element_form(v, walk) for k, v in value.items()}
        return _NOT_LAID if any(v is _NOT_LAID for v in entries.values()) else entries
    return _NOT_LAID

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lay a target's field defaults under a merged dict, as the base layer every source patches.

``build()``, ``resolve()`` and ``from_dict()`` lay the defaults a class declares as values
below the data they are given, through the merge's own combiner, so a pending list op or
index patch applies over a default as it would over a lower file holding it, and an
expression reads a default nobody set. A default nobody touched is recorded and taken out
again once expressions are resolved: construction applies it, as it always did.

No layer lies below the defaults, so a pending op where no default is laid is applied over
nothing, wherever the type says the node is a list: an expression then reads the list
construction builds. A patch over an expression is left as the merge carried it, the
expression its base, and settles once resolution has resolved it (:func:`settle_pending`).

Dev Notes:
    docs-dev/architecture/design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer
"""

from __future__ import annotations

import dataclasses
import enum
from typing import TYPE_CHECKING, Any, NamedTuple

from confarg import _defaults
from confarg._merge import (
    _SHAPE,
    ListOp,
    MergeAt,
    _apply_list_ops,
    _DeleteSentinel,
    _holds_list_ops,
    _is_pin_dict,
    _merge_existing_value,
    _replace_base,
)
from confarg._parse_cli import _locals_keys
from confarg._tags import _tag_named_struct
from confarg._typed_merge import TypedAt, merge_at, merge_root
from confarg._types import (
    _all_have_defaults,
    _dict_kv,
    _elem_type,
    _fixed_position,
    _fixed_seq_types,
    _is_seq_variant,
    _is_struct,
    _is_struct_like,
    _namedtuple_fields,
    _resolve_type,
    _struct_declared_defaults,
    _struct_fields,
    _struct_required,
    _union_args_no_none,
    _union_has_seq_variant,
    _union_tag_shadowed,
)
from confarg.dictexpr import contains_expression, escape_expressions
from confarg.exceptions import _spell_field_path
from confarg.typedload._coerce import _is_struct_variant, _registered_leaf_of, _type_kind, _TypeKind
from confarg.typedload._construct import _UNSET as _UNSET_POSITION
from confarg.typedload._construct import _is_typed_call, reads_as_new_value, unset_position

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from confarg._merge import MergeDict
    from confarg.dictexpr._expressions import Settler

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

    A key delete no layer met is met by none here either, so it deletes nothing: it is
    dropped, and so is a dict it alone filled, before any default is laid where it stood
    (:func:`_kept`). Below a sequence, a bare delete at an index is left for construction to
    refuse, and a namedtuple field's beside a base is left as it is.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer
    """
    walk = _Walk(union_tag, for_resolution)
    target = _resolve_type(target)
    if _is_struct_like(target):
        laid = _node(target, data, (), walk)
        if laid is _PRUNED:
            laid = _node(target, {}, (), walk)
    elif _defaults.ROOT_KEY in data:
        root = _node(target, data[_defaults.ROOT_KEY], (_defaults.ROOT_KEY,), walk)
        if root is _PRUNED:
            laid = {k: v for k, v in data.items() if k != _defaults.ROOT_KEY}
        else:
            laid = data if root is data[_defaults.ROOT_KEY] else {**data, _defaults.ROOT_KEY: root}
        laid = _with_namespaces_applied(laid, _locals_keys(target, union_tag), ())
    else:
        laid = data
    return LaidDefaults(laid, tuple(walk.untouched))


def settle_pending(target: Any, union_tag: str) -> Settler:
    """Return what resolution settles a node of pending ops into, for data of type *target*.

    A node carrying a base, most often an expression the merge kept below a patch over it,
    combines the base resolution resolved with the patch, by the merge's own combiner, as a
    lower layer holding the value would have (:func:`~confarg._merge._merge_existing_value`).
    What is left pending then, and a node of ops an expression stood in, is applied over
    nothing as before resolution. A node the type cannot read is left as it is.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#a-patch-over-an-expression-patches-its-value
    """
    root = merge_root(target, union_tag)
    walk = _Walk(union_tag, for_resolution=False)

    def settle(data: MergeDict, path: Sequence[str | ListOp], node: MergeDict) -> Any:
        at = _at_path(root, data, path)
        spelled = _spelled(tuple(path))
        if ListOp.BASE in node and not contains_expression(node[ListOp.BASE]):
            rest = {k: v for k, v in node.items() if k is not ListOp.BASE}
            settled: Any = _merge_existing_value(node[ListOp.BASE], rest, spelled, at) if rest else node[ListOp.BASE]
        else:
            settled = node
        tp = at.tp if isinstance(at, TypedAt) else Any
        laid = _node(tp, settled, tuple(path), walk)
        return settled if laid is _PRUNED else laid

    return settle


def _at_path(root: MergeAt, data: MergeDict, path: Sequence[str | ListOp]) -> MergeAt:
    """Return where the merge stands at *path* of *data*, each node read as the data holds it.

    An op's own key names no field: an item it holds is typed as an element of the list.
    """
    at, node = root, data
    for part in path:
        child = node.get(part) if isinstance(node, dict) else None
        if not isinstance(part, ListOp):
            at = at.child(part, node, None)
        node = child
    return at


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


def _node(tp: Any, node: Any, path: DataPath, walk: _Walk) -> Any:  # noqa: PLR0911  # one return per kind
    """Lay the defaults below *node*, which the data holds where the type is *tp*.

    ``_PRUNED`` when *node* is a dict its unmet deletes alone filled (:func:`_kept`).
    """
    tp = _resolve_type(tp)
    if not isinstance(node, dict | list) or _is_pin_dict(node) or _carries_an_expression(node):
        return node
    if _is_typed_call(node, tp):
        return _untyped(node)
    kind = _type_kind(tp)
    if kind is _TypeKind.STRUCT:
        cls = _struct_built_from(tp, node, walk.union_tag) if isinstance(node, dict) else None
        return _untyped(node) if cls is None else _struct(cls, node, path, walk)
    if kind is _TypeKind.UNION:
        return _union(tp, node, path, walk)
    if kind in _SEQUENCE_KINDS:
        return _sequence(tp, node, path, walk)
    if kind is _TypeKind.DICT and isinstance(node, dict):
        _, vt = _dict_kv(tp)
        return _kept(node, {k: v if isinstance(k, ListOp) else _node(vt, v, (*path, k), walk) for k, v in node.items()})
    return _untyped(node)


# What a node holding nothing but key deletes no layer met reads as: no node at all.
_PRUNED: Any = object()

# The ops whose value says what the list is, rather than what goes in it.
_STRUCTURAL_OPS = (ListOp.BASE, ListOp.DELETE, ListOp.DELETE_AFTER)


def _carries_an_expression(node: Any) -> bool:
    """Whether *node* is a node of ops one of whose structural values is an expression.

    Most often the base the merge carried below a patch over an expression: what lies below
    the patch is unknown until resolution resolves it, so no default is laid there and the
    ops wait for it (:func:`settle_pending`).

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#a-patch-over-an-expression-patches-its-value
    """
    return isinstance(node, dict) and any(op in node and contains_expression(node[op]) for op in _STRUCTURAL_OPS)


def _over_nothing(node: MergeDict, spelled: str, at: MergeAt) -> list[Any] | None:
    """Return the list the pending ops *node* holds make over what they carry or nothing, None if none.

    No layer lies below the defaults, so construction would build this list: an append, a
    base and its patch, and the deletes beside them. A delete with nothing to delete from is
    left for construction to refuse, and so is a node holding no op.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-pending-list-op-is-read-as-its-list
    """
    if ListOp.BASE not in node and ListOp.APPEND not in node:
        return None
    base = _replace_base(node, spelled) if ListOp.BASE in node else []
    return _apply_list_ops(base, node, spelled, at)


def _index_keyed(node: MergeDict) -> list[Any] | None:
    """Return the list an index-keyed dict with no gap spells, None for any other dict.

    Construction reads ``{"0": a, "1": b}`` as ``[a, b]``; one with a gap, a key no index
    spells or a bare delete is construction's to read or refuse.
    """
    from confarg.dictexpr._expressions import _list_index  # noqa: PLC0415  # the one reading of an index segment

    if not node or any(isinstance(v, _DeleteSentinel) for v in node.values()):
        return None
    indices = {_list_index(k) if isinstance(k, str) else None: v for k, v in node.items()}
    if set(indices) != set(range(len(node))):
        return None
    return [indices[i] for i in range(len(node))]


def _with_namespaces_applied(node: MergeDict, keys: Sequence[str], path: DataPath) -> MergeDict:
    """Return *node* with the pending ops below each local-variables namespace it holds applied over nothing.

    A local has no annotation, and an op only ever makes a list, so no type is needed to read
    one as the list it makes; nothing builds a namespace, so nothing else would.

    Dev Notes:
        docs-dev/architecture/locals.md#a-list-op-in-a-namespace-is-its-list
    """
    out = {k: _untyped_lists(v, (*path, k)) if k in keys else v for k, v in node.items()}
    return _copied_if_changed(node, out)


def _untyped_lists(value: Any, path: DataPath) -> Any:
    """Return *value* with each node of pending ops applied over nothing, at any depth, by the shape rule."""
    if isinstance(value, list):
        return _copied_if_changed(value, [_untyped_lists(v, (*path, i)) for i, v in enumerate(value)])
    if not isinstance(value, dict):
        return value
    if _holds_list_ops(value) and not _carries_an_expression(value):
        applied = _over_nothing(value, _spelled(path), _SHAPE)
        if applied is not None:
            return [_untyped_lists(v, (*path, i)) for i, v in enumerate(applied)]
    return _copied_if_changed(value, {k: _untyped_lists(v, (*path, k)) for k, v in value.items()})


def _is_gone(value: Any) -> bool:
    """Whether *value* is a key delete no layer met, or a dict holding nothing but such deletes."""
    return isinstance(value, _DeleteSentinel) or value is _PRUNED


def _kept(original: MergeDict, rebuilt: MergeDict) -> Any:
    """Return *rebuilt* without the keys whose value :func:`_is_gone`, ``_PRUNED`` if that empties it.

    A dict the data held empty stays: it was written so, not filled by a delete.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-field-default-is-the-base-layer.md#a-delete-meets-the-defaults-last
    """
    kept = {k: v for k, v in rebuilt.items() if not _is_gone(v)}
    if original and not kept:
        return _PRUNED
    return _copied_if_changed(original, kept)


def _untyped(node: Any) -> Any:
    """Drop the unmet key deletes below a node no type settles, as :func:`_kept` does, at every depth."""
    if not isinstance(node, dict):
        return node
    return _kept(node, {k: _untyped(v) for k, v in node.items()})


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
    if _holds_list_ops(node):
        sequence = _sequence_taking_ops(variants)
        if sequence is not None:
            return _sequence(sequence, node, path, walk)
    if not isinstance(node, dict) or walk.union_tag not in node or _union_tag_shadowed(tp, walk.union_tag):
        return _untyped(node)
    cls = _tagged_class(node[walk.union_tag])
    matching = [v for v in variants if cls is not None and _is_struct(v) and issubclass(cls, v)]
    return _struct(cls, node, path, walk) if len(matching) == 1 else _untyped(node)


def _sequence_taking_ops(variants: list[Any]) -> Any:
    """Return the sequence type a union's variants build a node of list ops as, None where none is certain.

    Only a sequence variant takes a list op, and construction builds the list there; where
    each is variable-length, the list the ops make is the same whichever builds it, typed by
    the element type they share, untyped where they differ. A fixed-length variant has no
    length to grow, so a node it may take is construction's.
    """
    sequences = [v for v in variants if _type_kind(v) in _SEQUENCE_KINDS]
    if not sequences or any(_fixed_seq_types(v) is not None for v in sequences):
        return None
    elements = {_elem_type(v) for v in sequences}
    return sequences[0] if len(elements) == 1 else list[Any]


def _struct(cls: Any, node: MergeDict, path: DataPath, walk: _Walk) -> Any:
    """Lay the defaults *cls* declares at its fields under *node*.

    A field holding only an unmet key delete reads as one the data omits; ``_PRUNED`` when
    every key of *node* is such a field, before any default is laid (:func:`_kept`).
    """
    try:
        fields = _struct_fields(cls)
        defaults = _struct_declared_defaults(cls)
        required = _struct_required(cls)
    except _INTROSPECTION_ERRORS:
        return _untyped(node)
    laid_at = {
        name: _merged_form(defaults[name], ft, walk) if name in defaults else _NOT_LAID for name, ft in fields.items()
    }
    held = {
        name: _held(node[name], ft, laid_at[name], (*path, name), walk) for name, ft in fields.items() if name in node
    }
    kept = _kept(node, {**node, **held})
    if kept is _PRUNED:
        return kept
    out = _with_namespaces_applied(dict(kept), _namespace_keys(cls, walk.union_tag), path)
    for name, ft in fields.items():
        fpath = (*path, name)
        laid = laid_at[name]
        if name in out or not walk.for_resolution:
            continue
        if laid is not _NOT_LAID:
            out[name] = laid
            walk.untouched.append(fpath)
        elif name in required and _is_struct_variant(ft) and _all_have_defaults(ft):
            # Construction builds such a field from {} (``_construct_struct``): its class's
            # defaults are what it will hold.
            out[name] = _struct(_resolve_type(ft), {}, fpath, _Walk(walk.union_tag, for_resolution=True))
            walk.untouched.append(fpath)
    return _copied_if_changed(node, out)


def _namespace_keys(cls: Any, union_tag: str) -> tuple[str, ...]:
    """Return the names of the local-variables namespace *cls* holds, none where its members cannot be read."""
    try:
        return _locals_keys(cls, union_tag)
    except _INTROSPECTION_ERRORS:
        return ()


def _held(value: Any, ft: Any, laid: Any, fpath: DataPath, walk: _Walk) -> Any:
    """Return what a field the data sets holds with the defaults laid below it, a bare delete as it is.

    A fixed-length position a delete unsets is taken out of the default too: the merge keeps
    the delete in the keyed form it leaves (:func:`~confarg._merge._unset_positions`), and,
    having met the default, it is dropped here, the position left for construction to fill
    as it fills an unset one (BUG-243).
    """
    if isinstance(value, _DeleteSentinel):
        return value
    if isinstance(laid, list) and _patches_a_list(value, ft, walk.union_tag):
        value = _merge_existing_value(laid, value, _spelled(fpath), merge_at(ft, walk.union_tag))
        if isinstance(value, dict) and ListOp.BASE not in value:
            value = {k: v for k, v in value.items() if not isinstance(v, _DeleteSentinel)}
    return _node(ft, value, fpath, walk)


def _patches_a_list(value: Any, ft: Any, union_tag: str) -> bool:
    """Whether *value*, at a field of type *ft*, is a patch the field's list default is the base of.

    A dict carrying its own base, a cast pin, or one construction reads as a value of its own
    (a tag, a typed call: :func:`~confarg.typedload._construct.reads_as_new_value`) replaces
    what lies below rather than patching it, so the default is not laid under it.
    """
    return (
        isinstance(value, dict)
        and (_is_seq_variant(ft) or _union_has_seq_variant(ft))
        and ListOp.BASE not in value
        and not _is_pin_dict(value)
        and not reads_as_new_value(value, ft, union_tag)
    )


def _sequence(tp: Any, node: Any, path: DataPath, walk: _Walk) -> Any:
    """Lay defaults below each element a sequence node holds: a list's items, a patch's values.

    ``_PRUNED`` when, with no base, its index patches held nothing but unmet deletes
    (:func:`_lay_index_patches`).
    """
    element = _element_type(tp)
    if isinstance(node, list):
        return _items(node, element, path, walk)
    variable = _fixed_seq_types(tp) is None
    if variable and (applied := _applied_over_nothing(tp, node, path, walk)) is not None:
        return _items(applied, element, path, walk)
    out = dict(node)
    base = node.get(ListOp.BASE)
    if isinstance(base, list):
        out[ListOp.BASE] = _items(base, element, (*path, ListOp.BASE), walk)
    appended = node.get(ListOp.APPEND)
    if isinstance(appended, list):
        out[ListOp.APPEND] = _items(appended, lambda _: element(None), (*path, ListOp.APPEND), walk)
    elif isinstance(appended, dict):
        out[ListOp.APPEND] = _item(element(None), appended, (*path, ListOp.APPEND), walk)
    if isinstance(base, list):
        # Beside a base, an index value refines the element it reaches, which holds its own.
        return _copied_if_changed(node, out)
    fixed = not variable
    _lay_index_patches(out, element, path, walk, fixed=fixed)
    if node and not out:
        return _PRUNED
    if fixed:
        _lay_unset_positions(tp, out, path, walk)
    elif (positions := _index_keyed(out)) is not None:
        return positions
    return _copied_if_changed(node, out)


def _applied_over_nothing(tp: Any, node: MergeDict, path: DataPath, walk: _Walk) -> list[Any] | None:
    """Return the list the ops a variable-length sequence node of type *tp* holds make, None if it holds none."""
    if not _holds_list_ops(node):
        return None
    return _over_nothing(node, _spelled(path), merge_at(tp, walk.union_tag))


def _lay_unset_positions(tp: Any, out: MergeDict, path: DataPath, walk: _Walk) -> None:
    """Lay, at each position the keyed fixed-length node *out* leaves unset, what construction fills it with, in place.

    So a reference reads what the field builds to (:func:`~confarg.typedload._construct.unset_position`):
    a namedtuple field's class default, a fixed tuple's ``None`` where its type takes it. Each
    is recorded as untouched, and taken out again before construction, which fills it itself.
    Only for resolution, and only on a node holding no pending op.
    """
    if not walk.for_resolution or _holds_list_ops(out):
        return
    held = {_fixed_position(tp, k) for k in out}
    names = list(_namedtuple_fields(tp)) if _type_kind(tp) is _TypeKind.NAMEDTUPLE else []
    for i, et in enumerate(_fixed_seq_types(tp) or ()):
        if i in held or (value := unset_position(tp, i)) is _UNSET_POSITION:
            continue
        laid = _merged_form(value, et, walk)
        if laid is _NOT_LAID:
            continue
        key = names[i] if names else str(i)
        out[key] = laid
        walk.untouched.append((*path, key))


def _lay_index_patches(
    out: MergeDict,
    element: Callable[[Any], Any],
    path: DataPath,
    walk: _Walk,
    *,
    fixed: bool,
) -> None:
    """Lay defaults below each index patch of *out*, a sequence node with no base, in place.

    A patch its unmet deletes alone filled is removed, and so is a fixed-length position's
    bare delete that met nothing, which reads as a position the data omits (BUG-98, BUG-243);
    a list index's bare delete stays for construction to refuse.
    """
    for k, v in list(out.items()):
        if isinstance(k, ListOp):
            continue
        if isinstance(v, _DeleteSentinel):
            if fixed:
                del out[k]
            continue
        laid = _node(element(k), v, (*path, k), walk)
        if laid is _PRUNED:
            del out[k]
        else:
            out[k] = laid


def _items(items: list[Any], element: Callable[[Any], Any], path: DataPath, walk: _Walk) -> list[Any]:
    """Lay defaults below each item of *items*, typed by its position."""
    return _copied_if_changed(items, [_item(element(i), v, (*path, i), walk) for i, v in enumerate(items)])


def _item(tp: Any, item: Any, path: DataPath, walk: _Walk) -> Any:
    """Lay defaults below one item, which keeps its place: an item has no layer below for a delete to meet."""
    laid = _node(tp, item, path, walk)
    return item if laid is _PRUNED else laid


def _element_type(tp: Any) -> Callable[[Any], Any]:
    """Return what a sequence of type *tp* holds at a key: a position, or a namedtuple's field name.

    A fixed-length sequence reads the key by :func:`~confarg._types._fixed_position`, as
    construction does; a key naming no position holds ``Any``.
    """
    positions = _fixed_seq_types(tp)

    def element(key: Any) -> Any:
        if positions is None:
            return _elem_type(tp)
        position = _fixed_position(tp, key)
        return Any if position is None else positions[position]

    return element


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
    if value is None or isinstance(value, (bool, int, float)) or _registered_leaf_of(value) is not None:
        return value
    if isinstance(value, tuple | list):
        items = [_element_form(v, walk) for v in value]
        return _NOT_LAID if any(i is _NOT_LAID for i in items) else items
    if isinstance(value, dict):
        entries = {k: _element_form(v, walk) for k, v in value.items()}
        return _NOT_LAID if any(v is _NOT_LAID for v in entries.values()) else entries
    return _NOT_LAID

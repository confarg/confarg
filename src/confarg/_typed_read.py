# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What an expression reads in a target's data: an Enum or registered leaf as its object.

The merged dict holds such a leaf as it was written, on every channel. An expression reads
it as the object construction will build, wherever one type is certain, so ``RED``, ``red``
and a default's ``Color.RED`` are one member, and a path is a ``Path`` whichever channel set
it. The type at a position is the one the typed merge steps to (:class:`~confarg._typed_merge.TypedAt`),
reading the tag or the spec each node holds.

Dev Notes:
    docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, cast

from confarg import _defaults
from confarg._callable import _COMPUTATION_OPENERS
from confarg._tags import class_named
from confarg._typed_merge import TypedAt, merge_root
from confarg._types import _is_union, _resolve_type, _union_args_no_none
from confarg.exceptions import ConfargWarning
from confarg.typedload._coerce import _is_registered_leaf, read_as_object
from confarg.typedload._construct import construct, read_union_leaf

if TYPE_CHECKING:
    from collections.abc import Sequence

    from confarg._merge import ListOp, MergeAt, MergeDict


class TypedReading:
    """The reading of a configuration of one target type that ``resolve_expressions`` reads its values through.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
    """

    __slots__ = ("_root",)

    def __init__(self, target: Any) -> None:
        self._root = merge_root(target)

    def __call__(self, data: MergeDict, path: Sequence[str | ListOp], value: Any) -> Any:
        """Return what an expression reads of *value*, which *data* holds at *path*.

        *path* is named as the data names it, a list element by its position, so each step
        reaches a node *data* holds.
        """
        at: MergeAt = self._root
        node: Any = data
        for segment in path:
            at = at.child(segment, node, None)
            # A list element is named by its position, never by an op.
            node = node[segment] if isinstance(node, dict) else node[int(cast("str", segment))]
        return _read(at, value)


def _read(at: MergeAt, value: Any) -> Any:
    """Return *value*, held where the typed merge stands at *at*, each leaf read by :func:`_read_leaf`.

    A dict whose class key builds a registered leaf is that leaf (:func:`_read_tagged_leaf`).
    Any other dict or a list is walked, and copied only where a leaf in it was read as an object.
    Every expression a read reaches has resolved, the dependency graph orders it first, so text
    spelling ``${...}`` is the literal an escape resolves to, read as any other text.
    """
    if isinstance(value, dict):
        if isinstance(at, TypedAt) and (leaf := _read_tagged_leaf(at.tp, value)) is not value:
            return leaf
        items = {k: _read(at.child(k, value, None), v) for k, v in value.items()}
        return value if all(items[k] is v for k, v in value.items()) else items
    if isinstance(value, list):
        elements = [_read(at.child(str(i), value, None), v) for i, v in enumerate(value)]
        return value if all(a is b for a, b in zip(elements, value, strict=True)) else elements
    if not isinstance(at, TypedAt):
        return value
    return _read_leaf(at.tp, value)


def _read_leaf(ft: Any, value: Any) -> Any:
    """Return what an expression reads of the resolved leaf *value* at a field of type *ft*: the object it builds.

    A union of several variants reads it as the variant construction picks
    (:func:`read_union_leaf`); one type, an optional included, by :func:`read_as_object`, whose
    leaf coercion reads no tag.
    """
    tp = _resolve_type(ft)
    if _is_union(tp) and len(_union_args_no_none(tp)) > 1:
        return read_union_leaf(tp, value)
    return read_as_object(tp, value)


def _read_tagged_leaf(tp: Any, value: MergeDict) -> Any:
    """Return what an expression reads of the dict *value* at a node of type *tp*: the leaf its class key builds.

    A class key naming a registered leaf builds it from its fields wherever construction takes
    the tag, at the leaf, a struct it subclasses, a union, an ``Any`` or a Callable alike, so
    *value* reads as what :func:`construct` builds there. The class itself must be registered:
    an unregistered subclass of one is a struct, which reads as its dict. *value* reads as
    written where it names no registered leaf, where construction refuses it, and where it
    holds what construction has yet to compute (:func:`_computes`): text spelling ``${...}``
    is a literal, resolution having resolved every expression the read reaches, which builds
    as any other text. The reading never warns: construction warns of what it builds.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
    """
    if _defaults.CLASS_KEY not in value or _computes(value):
        return value
    cls = class_named(value[_defaults.CLASS_KEY])
    if cls is None or not _is_registered_leaf(cls):
        return value
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConfargWarning)
            return construct(tp, value)
    except Exception:  # noqa: BLE001  # a constructor may raise anything (BUG-269); construction reports it
        return value


def _computes(value: Any) -> bool:
    """Return whether *value* holds, at any depth, a ``call:`` or a ``bind:``: a value no reading has.

    A call's result is construction's, which an expression reads none of.
    """
    if isinstance(value, dict):
        return any(k in _COMPUTATION_OPENERS for k in value) or any(_computes(v) for v in value.values())
    if isinstance(value, list):
        return any(_computes(v) for v in value)
    return False

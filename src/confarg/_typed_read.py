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

from typing import TYPE_CHECKING, Any, cast

from confarg._typed_merge import TypedAt, merge_root
from confarg._types import _is_union, _resolve_type, _union_args_no_none
from confarg.dictexpr import contains_expression
from confarg.typedload._coerce import read_as_object
from confarg.typedload._construct import read_union_leaf

if TYPE_CHECKING:
    from collections.abc import Sequence

    from confarg._merge import ListOp, MergeAt, MergeDict


class TypedReading:
    """The reading of a configuration of one target type that ``resolve_expressions`` reads its values through.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
    """

    __slots__ = ("_root",)

    def __init__(self, target: Any, union_tag: str) -> None:
        self._root = merge_root(target, union_tag)

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
    """Return *value*, held where the typed merge stands at *at*, each leaf read by :func:`read_as_object`.

    A dict or a list is walked, and copied only where a leaf in it was read as an object.
    """
    if isinstance(value, dict):
        items = {k: _read(at.child(k, value, None), v) for k, v in value.items()}
        return value if all(items[k] is v for k, v in value.items()) else items
    if isinstance(value, list):
        elements = [_read(at.child(str(i), value, None), v) for i, v in enumerate(value)]
        return value if all(a is b for a, b in zip(elements, value, strict=True)) else elements
    if not isinstance(at, TypedAt):
        return value
    return _read_leaf(at.tp, value)


def _read_leaf(ft: Any, value: Any) -> Any:
    """Return what an expression reads of the leaf *value* at a field of type *ft*: the object construction builds.

    A union of several variants reads it as the variant construction picks
    (:func:`read_union_leaf`); one type, an optional included, by :func:`read_as_object`.
    """
    tp = _resolve_type(ft)
    if _is_union(tp) and len(_union_args_no_none(tp)) > 1 and not contains_expression(value):
        return read_union_leaf(tp, value)
    return read_as_object(tp, value)

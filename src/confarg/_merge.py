# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Deep merge of the intermediate dicts, and the list/dict patch sentinels it understands.

Dev Notes:
    docs-dev/architecture/pipeline/deep-merge.md#deep-merge-semantics
"""

from __future__ import annotations

import enum
import json
from typing import TYPE_CHECKING, Any

from confarg import _defaults
from confarg.exceptions import ConfargError, InvalidConfigFileError, TypeCoercionError

if TYPE_CHECKING:
    from collections.abc import Sequence


class ListOp(enum.Enum):
    """A list operation that `merge()` leaves pending in the dict it returns, for `build()` to apply.

    A dict `merge()` returns may hold one of these as a key, beside or instead of the list it
    patches: an append with no base list below it yet, or an index patch that needs the
    field's type to apply. No string equals one, so a key a file, a variable or a flag spells
    the same way is always data. `str()` gives the reserved key a configuration file writes
    the op with, which is how `dump_file()` writes it and how `merge(files=[...])` reads it back.

    Example::

        raw = confarg.merge(Config, argv=["--tags+", "x"])
        # {'tags': {ListOp.APPEND: ['x']}}
        str(confarg.ListOp.APPEND)  # '__append__'

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#no-channel-types-an-op
    """

    #: Append these items to the list. The value is a list or a scalar (single-value append);
    #: every producer stores one of those two shapes.
    APPEND = _defaults.APPEND_KEY

    #: Delete these indices from the list. The value is a sorted list of integers (original
    #: indices before deletion).
    DELETE = _defaults.DELETE_KEY

    #: Replace the base with this value before applying the other operations. Produced when a
    #: whole-list value is followed by a patch or append; the value is the replacement list.
    #: Also produced when a whole-field delete is followed by an op at or below its path; the
    #: value is then ``DICT_DELETE``: nothing lies below the ops.
    BASE = _defaults.BASE_KEY

    #: Delete these indices after the appends have been applied. Produced by the CLI parser when
    #: ``--field.N-`` appears after ``--field+``. The value is a sorted list of post-append indices.
    DELETE_AFTER = _defaults.DELETE_AFTER_KEY

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"ListOp.{self.name}"


#: A dict the merge produces or reads: data keyed by name, and the list ops pending on it.
type MergeDict = dict[str | ListOp, Any]

#: Every list op, keyed by the reserved key a file writes it with.
MERGE_OP_KEYS: dict[str, ListOp] = {op.value: op for op in ListOp}

# The suffixes a flag or a variable carries on its path to append to the field it names
# (``--xs+``, ``APP_XS+``) or to delete it (``--d.k-``, ``--xs.0-``). A file spells both in the
# value (``_read_file_ops``), since its keys are its data.
APPEND_SUFFIX = "+"
DELETE_SUFFIX = "-"


class _DeleteSentinel:
    """Sentinel value indicating that a dict key should be removed during merge."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "_DELETE_"


# Singleton sentinel stored as a dict value to mark that key for deletion.
DICT_DELETE: _DeleteSentinel = _DeleteSentinel()

# A delete that already removed its key from the part of its source below it, kept to delete in
# the layers below too (_merge_within_source). Every merge reads it as DICT_DELETE; once every
# layer is in, one no layer met is dropped (_drop_deleted_bases), where DICT_DELETE survives.
_SPENT_DELETE: _DeleteSentinel = _DeleteSentinel()


def _spent_if_met(below: MergeDict, key: Any, at: MergeAt | None = None) -> _DeleteSentinel:
    """Return the delete of *key* written over *below*, the part of its own source before it, *at* where they stand.

    Spent when *below* gave it a key to remove (a spent delete there had one too), any key
    *at* reads as *key* included (:meth:`MergeAt.key_identity`), plain otherwise.
    """
    at = at or MergeAt()
    identity = at.key_identity(key)
    met = [below[k] for k in below if at.key_identity(k) == identity]
    return _SPENT_DELETE if any(v is not DICT_DELETE for v in met) else DICT_DELETE


def _written_within_source(below: Any, over: Any, *, at: MergeAt) -> Any:
    """Return what writing *over* where *below* lies leaves there, both parts of one source, *at* where they stand.

    Two dicts merge by :func:`_merge_within_source`, which keeps their deletes for the layers
    below. A delete over a value is kept spent (:func:`_spent_if_met`), and anything else is
    written by :func:`_written_over`: a dict over a delete keeps it as its base, a list or a
    scalar replaces what lay there.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too
    """
    if isinstance(below, dict) and isinstance(over, dict):
        return _merge_within_source(below, over, at=at)
    if isinstance(over, _DeleteSentinel):
        return over if over is _SPENT_DELETE else _spent_if_met({"": below}, "")
    return _written_over(below, over)


def _to_append_list(val: Any) -> list[Any]:
    """Convert the value stored under ListOp.APPEND to a flat list of items.

    Every producer stores a list (or set/tuple) or a scalar; a dict never reaches
    here — the index-keyed dict form is a construct-time concern, handled in
    ``typedload._construct``, not an append value.
    """
    if isinstance(val, list | set | frozenset | tuple):
        return list(val)
    return [val]  # scalar single-value append


def _read_file_ops(d: Any, loc: str, path: tuple[str, ...]) -> Any:
    """Read the reserved op keys of one dict of a file's document, at *path* in the document *loc*, as their markers.

    ``__append__``, ``__delete__``, ``__delete_after__`` and ``__base__`` become the keys of
    ``MERGE_OP_KEYS``; every other key is data, whatever its spelling. ``__unset__`` is read
    before, by the walk (``_files._resolve_dict``), which hands the rest of its dict here. Only
    a configuration document's dicts are read, each once its values are resolved, so an
    ``__append__`` appends what an include under it brings; no merge reads a key as an op, so
    a value argv or the environment decodes is data.

    An append's items are list items (:func:`_as_list_item`): a single one is checked here, a
    list's by the walk. A base is a list, so a delete standing as one is refused.

    Returns:
        *d* itself when it holds no op key, and when it is no dict.

    Raises:
        InvalidConfigFileError: If the base, or a single appended item, is a bare node delete.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-file-spells-an-op-in-its-value.md#a-file-spells-an-op-in-its-value
    """
    if not isinstance(d, dict) or not any(key in MERGE_OP_KEYS for key in d):
        return d
    result: MergeDict = {MERGE_OP_KEYS.get(key, key): value for key, value in d.items()}
    if isinstance(result.get(ListOp.BASE), _DeleteSentinel):
        reason = f"{str(ListOp.BASE)!r} holds a list; a node is deleted below its ops by writing the delete beside them"
        raise InvalidConfigFileError.misplaced_unset(_defaults.UNSET_KEY, loc, (*path, str(ListOp.BASE)), reason)
    if ListOp.APPEND in result and not isinstance(result[ListOp.APPEND], list):
        result[ListOp.APPEND] = _as_list_item(result[ListOp.APPEND], loc, (*path, str(ListOp.APPEND)))
    return result


def _as_list_item(value: Any, loc: str, path: tuple[str, ...]) -> Any:
    """Return *value*, at *path* in the document *loc*, as an item of a list.

    An item has no layer below it, so every delete it holds is dropped (:func:`_without_key_deletes`).

    Raises:
        InvalidConfigFileError: If *value* is a node delete itself, which would leave nothing in the item's place.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-file-spells-an-op-in-its-value.md#where-a-delete-has-no-meaning
    """
    if isinstance(value, _DeleteSentinel):
        reason = "a list item has no layer below it, so it would delete nothing"
        raise InvalidConfigFileError.misplaced_unset(_defaults.UNSET_KEY, loc, path, reason)
    return _without_key_deletes(value)


def _resolve_index(orig_idx: int, length: int, key: str, kind: str) -> int:
    """Validate *orig_idx* against a list of *length* and return the wrapped index.

    Negative indices count from the end; out-of-range indices raise ``ConfargError``.
    *kind* is ``"delete"`` or ``"patch"`` and only selects the error wording.
    """
    idx = orig_idx + length if orig_idx < 0 else orig_idx
    if 0 <= idx < length:
        return idx
    _rng = "(the list is empty)" if not length else f"(valid indices {-length} to {length - 1})"
    if kind == "delete":
        msg = f"Cannot delete index {orig_idx} from '{key}': the list has {length} element(s) {_rng}."
    else:
        msg = (
            f"Cannot patch list '{key}' at index {orig_idx}:"
            f" the list has {length} element(s) {_rng}."
            " Use the + append syntax (e.g. --field+ for CLI) to add new elements."
        )
    raise ConfargError(msg)


def _replace_base(ops: MergeDict, key: str) -> list[Any]:
    """Return a copy of the base list *ops* carries under ``ListOp.BASE``.

    The one reader of the key, for the merge and for construction alike: a value that is no
    list or tuple -- which only a file writing the key itself can hold -- is refused rather than
    read with ``list()``, which would split a string into its characters.

    Raises:
        TypeCoercionError: If the value is no list or tuple.
    """
    base = ops[ListOp.BASE]
    if not isinstance(base, list | tuple):
        raise TypeCoercionError.op_not_a_list(str(ListOp.BASE), "a list", type(base).__name__, base, key)
    return list(base)


def _delete_indices(ops: MergeDict, delete_key: ListOp, key: str) -> list[int]:
    """Return the indices *ops* deletes under *delete_key*, ``ListOp.DELETE`` or ``ListOp.DELETE_AFTER``.

    The one reader of the two keys: a value that is no list of integers -- which only a file
    writing the key itself can hold -- is refused rather than iterated.

    Raises:
        TypeCoercionError: If the value is no list or tuple of integers.
    """
    indices = ops[delete_key]
    if not isinstance(indices, list | tuple) or not all(type(i) is int for i in indices):
        raise TypeCoercionError.op_not_a_list(
            str(delete_key), "a list of indices", type(indices).__name__, indices, key
        )
    return list(indices)


def _apply_list_ops(
    working: list[Any],
    ops: MergeDict,
    key: str,
    at: MergeAt,
) -> list[Any]:
    """Apply list mutation operations from *ops* onto *working* in order, *at* where the list stands.

    Operations are applied in a fixed semantic order regardless of dict iteration:
    1. Pre-append deletions (ListOp.DELETE): remove indices from *working*.
    2. Appends (ListOp.APPEND): extend *working*.
    3. Post-append deletions (ListOp.DELETE_AFTER): remove indices
       from the post-append *working* (used when a CLI delete follows an append).
    4. Index patches (integer string keys, including negative): replace elements.

    ListOp.BASE is ignored here; the caller already used it to set *working*.

    Raises:
        ConfargError: If an index is out of range, or a patch key is no integer.
        TypeCoercionError: If an index patch is a bare node delete, which a list spells as a
            ``ListOp.DELETE`` instead.
    """
    # 1. Pre-append deletions
    if ListOp.DELETE in ops:
        del_set = {_resolve_index(i, len(working), key, "delete") for i in _delete_indices(ops, ListOp.DELETE, key)}
        working = [item for i, item in enumerate(working) if i not in del_set]

    # 2. Appends
    if ListOp.APPEND in ops:
        working = working + _to_append_list(ops[ListOp.APPEND])

    # 3. Post-append deletions
    if ListOp.DELETE_AFTER in ops:
        after = _delete_indices(ops, ListOp.DELETE_AFTER, key)
        del_set = {_resolve_index(i, len(working), key, "delete") for i in after}
        working = [item for i, item in enumerate(working) if i not in del_set]

    # 4. Index patches
    for ik, iv in ops.items():
        if isinstance(ik, ListOp):
            continue
        try:
            orig_idx = int(ik)
        except ValueError:
            msg = (
                f"Cannot patch list '{key}' with non-integer key {ik!r}."
                " List patches must use integer string keys (e.g. {'0': ..., '1': ...})."
            )
            raise ConfargError(msg) from None
        if isinstance(iv, _DeleteSentinel):
            raise TypeCoercionError.index_unset(_defaults.UNSET_KEY, str(ListOp.DELETE), ik, key)
        idx = _resolve_index(orig_idx, len(working), key, "patch")
        working = list(working)  # ensure mutability
        # A list/tuple element + index-keyed dict recurses through _apply_list_ops, a dict
        # element + dict patch deep-merges, and anything else is replaced by iv.
        working[idx] = _merge_existing_value(working[idx], iv, key, at.child(ik, None, None))

    return working


def _patch_needs_the_type(base: list[Any], ops: MergeDict, at: MergeAt) -> bool:
    """Whether *ops* is a pure patch whose meaning over *base* depends on the target type, *at* where it stands.

    A key that is no integer names a namedtuple field or nothing, and an index outside
    *base* fills a fixed tuple's slot or overruns a list. At a fixed-length node, a key is
    an index only as construction reads one (:func:`~confarg._types._spelled_position`,
    BUG-142), so ``01`` is left to construction to refuse. Such a patch is deferred to
    ``build()`` with the base carried along. Patches with append/delete keys return
    False so ``_apply_list_ops`` handles them (and raises its specific errors).

    Dev Notes:
        docs-dev/architecture/pipeline/merge-build-contract.md#merge-build-contract
    """
    from confarg._types import _spelled_position  # noqa: PLC0415  # import cycle: _types reads _list_index

    if any(k in ops for k in (ListOp.APPEND, ListOp.DELETE, ListOp.DELETE_AFTER)):
        return False
    n = len(base)
    fixed = at.fixed_length() is not None
    for k in ops:
        if isinstance(k, ListOp):  # the base, as every other op returned above
            continue
        try:
            i = _spelled_position(k) if fixed else int(k)
        except (TypeError, ValueError):
            return True
        if i is None or not -n <= i < n:
            return True
    return False


def _is_pin_dict(data: Any) -> bool:
    """Return whether *data* spells the file-side cast pin: exactly the ``__cast__`` and ``__value__`` keys.

    The shape half of ``typedload._construct._try_pinned_dict``, which resolves it. A pin is a
    value, not a patch: the merge lets it replace what lies below as a scalar would, and
    construction reads it wherever it stands (BUG-210).

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#cast-pinning-in-files
    """
    return isinstance(data, dict) and data.keys() == {_defaults.CAST_KEY, _defaults.VALUE_KEY}


class MergeAt:
    """What the merge knows of the type where it stands, which decides whether a value replaces or refines.

    This one knows no type, so it reads the shape alone: a dict naming the union tag or
    holding a ``call`` key is a new value, which replaces what lies below. It is the rule
    for a merge given no target, and the fallback of the typed reading
    (:class:`confarg._typed_merge.TypedAt`) where the type cannot tell.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines
    """

    __slots__ = ("union_tag",)

    def __init__(self, union_tag: str | None = None) -> None:
        self.union_tag = union_tag

    def replaces(self, override: MergeDict) -> bool:
        """Return whether the dict *override* is a value of its own, which replaces what lies below."""
        return (self.union_tag is not None and self.union_tag in override) or _defaults.CALL_KEY in override

    def opened(self, below: Any) -> Any:
        """Return what *below* is to a dict that refines it: here, itself."""
        return below

    def fixed_length(self) -> Any:
        """Return the fixed tuple or namedtuple type this node is, None where it is none: here, None."""
        return None

    def key_identity(self, key: Any) -> Any:
        """Return what *key* is to this node, so two keys with one identity are one key: here, its spelling.

        No type reads the node, so a key is what JSON writes it as (:func:`_key_spelling`).

        Dev Notes:
            docs-dev/architecture/pipeline/deep-merge.md#which-keys-are-one-key
        """
        return _key_spelling(key)

    def child(self, key: str | ListOp, below: Any, over: Any) -> MergeAt:  # noqa: ARG002  # the typed reading's signature
        """Return where the merge stands at *key* of the node *below* and *over* merge at."""
        return self

    def at_path(self, path: Sequence[str]) -> MergeAt:
        """Return where the merge stands at *path* below this node, knowing nothing of what the data holds."""
        at = self
        for part in path:
            at = at.child(part, None, None)
        return at


def _replaces_what_lies_below(bv: Any, val: Any, at: MergeAt) -> bool:
    """Whether the override *val* replaces *bv* outright rather than patching it.

    A cast pin is a value, and so is a dict *at* reads as one (a union tag, an opener), so
    they replace a list or a dict below them as a scalar would. A pin below is a value too,
    so a dict over it replaces it as a dict over a scalar does, rather than merging into the
    pin's two keys (BUG-239). An override carrying its own base (``ListOp.BASE``) replaces a
    dict base: the patches beside that base address it, not whatever an earlier layer held. A
    base that is a whole-field delete replaces a list base too.
    """
    if _is_pin_dict(val) or (isinstance(val, dict) and (_is_pin_dict(bv) or at.replaces(val))):
        return True
    return isinstance(val, dict) and ListOp.BASE in val and (val[ListOp.BASE] is DICT_DELETE or isinstance(bv, dict))


def _merge_existing_value(bv: Any, val: Any, key: str, at: MergeAt) -> Any:
    """Compute the merged value when *key* exists in both base and override, *at* where it stands.

    An override that replaces what lies below (:func:`_replaces_what_lies_below`) is kept
    whole. A scalar below a dict that refines it is first opened into what it means there
    (:meth:`MergeAt.opened`), so the dict refines it rather than replacing it. A dict's own
    key ``'*'`` is no base, whatever it holds: no channel spells the marker.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#deep-merge-semantics
    """
    if _replaces_what_lies_below(bv, val, at):
        return val
    if isinstance(val, dict):
        bv = at.opened(bv)
    if isinstance(bv, dict) and isinstance(val, dict):
        if ListOp.APPEND in bv and ListOp.APPEND in val:
            combined = _to_append_list(bv[ListOp.APPEND]) + _to_append_list(val[ListOp.APPEND])
            rest = _deep_merge(
                {k: v for k, v in bv.items() if k != ListOp.APPEND},
                {k: v for k, v in val.items() if k != ListOp.APPEND},
                at=at,
            )
            return {**rest, ListOp.APPEND: combined}
        if ListOp.DELETE in bv and ListOp.DELETE in val:
            combined_del = sorted(
                set(_delete_indices(bv, ListOp.DELETE, key)) | set(_delete_indices(val, ListOp.DELETE, key)),
            )
            rest = _deep_merge(
                {k: v for k, v in bv.items() if k != ListOp.DELETE},
                {k: v for k, v in val.items() if k != ListOp.DELETE},
                at=at,
            )
            return {**rest, ListOp.DELETE: combined_del}
        return _deep_merge(bv, val, at=at)
    if isinstance(bv, list) and isinstance(val, dict):
        return _merge_list_base(bv, val, key, at)
    return val


def _merge_list_base(bv: list[Any], val: MergeDict, key: str, at: MergeAt) -> Any:
    """Combine a list base *bv* with an override patch dict *val*."""
    if ListOp.BASE in val:
        base = _replace_base(val, key)
        if _patch_needs_the_type(base, val, at):
            # The override's own base replaces *bv*; what its patch means is still the type's.
            return val
        return _apply_list_ops(base, val, key, at)
    if _patch_needs_the_type(bv, val, at):
        # Defer to build(): an out-of-range index is an error for a list, a slot for a tuple;
        # a name key is an error for a list, a field for a namedtuple.
        return {ListOp.BASE: list(bv), **val}
    return _apply_list_ops(list(bv), val, key, at)


#: The merge with no type to read: the shape rule, with no union tag.
_SHAPE = MergeAt()


def _key_spelling(key: Any) -> Any:
    """Return JSON's spelling of a key that is no string, *key* itself otherwise.

    What a key is where no type reads it. JSON writes every key as text, as argv and the
    environment spell theirs, so a YAML file's ``1``, ``true``, ``null`` and ``1.5`` are
    ``"1"``, ``"true"``, ``"null"`` and ``"1.5"``, and a string meets them only so spelled:
    ``01`` and ``True`` stay other keys. A key JSON cannot write (a date) is itself, and so
    is a list op's marker.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#which-keys-are-one-key
    """
    if key is None or (isinstance(key, bool | int | float) and not isinstance(key, enum.Enum)):
        return json.dumps(key)
    return key


def _key_index(node: MergeDict, at: MergeAt) -> dict[Any, list[Any]]:
    """Return the keys of *node* by their identity *at* reads (:meth:`MergeAt.key_identity`), in *node*'s order."""
    index: dict[Any, list[Any]] = {}
    for k in node:
        index.setdefault(at.key_identity(k), []).append(k)
    return index


def _met_key(node: MergeDict, key: Any, at: MergeAt) -> Any:
    """Return the key of *node* that *key* is to the type *at* reads, *key* itself when *node* holds none.

    The last such key, which construction builds the value of, so a write refines what it
    will read. The key a lower part spelled is kept, and with it its place.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#which-keys-are-one-key
    """
    if key in node:
        return key
    identity = at.key_identity(key)
    met = [k for k in node if at.key_identity(k) == identity]
    return met[-1] if met else key


def _deep_merge(
    base: MergeDict,
    override: MergeDict,
    *,
    at: MergeAt = _SHAPE,
) -> MergeDict:
    """Recursively merge override into base, with override winning on conflict.

    Dict values are merged recursively.  Special override values:

    - ``DICT_DELETE`` as a value → removes that key from the result.
    - ``{ListOp.BASE: list}`` as a value for a list base → replaces the base
      list, then applies any additional append, delete or integer-key operations.
    - ``{ListOp.APPEND: items}`` as a value for a list base → appends items.
    - ``{ListOp.DELETE: [i, j]}`` as a value for a list base → deletes original indices i, j.
    - ``{"N": v}`` (integer string keys) as a value for a list base → patches by index.

    An override that *at* reads as a value of its own (:meth:`MergeAt.replaces`: a union
    tag, an opener) discards the base entirely, at every depth.

    Args:
        base: The base dict to merge into.
        override: The dict whose values take precedence.
        at: Where the two dicts stand, which reads the type there; the shape rule with no
            union tag by default.

    Returns:
        A new dict containing the merged result.

    Raises:
        ConfargError: If a delete index is out of range, or if a list patch beside an
            append or a delete uses an out-of-range index or a non-integer key.
    """
    if at.replaces(override):
        return dict(override)

    # Copy base, skipping any DICT_DELETE sentinels left over from normalization -- but not
    # a deleted base, which still cuts its node off from the layers merged under it later.
    result = {k: v for k, v in base.items() if k == ListOp.BASE or not isinstance(v, _DeleteSentinel)}

    # A key meets every key of the base it is one key with to the type (BUG-244).
    index = _key_index(result, at)
    for key, val in override.items():
        identity = at.key_identity(key)
        met = index.get(identity, [])
        if isinstance(val, _DeleteSentinel):
            for k in met:
                result.pop(k, None)
            index.pop(identity, None)
        elif met:
            k = met[-1]
            result[k] = _merge_existing_value(result[k], val, str(k), at.child(k, base, override))
        else:
            result[key] = val
            index[identity] = [key]
    return result


def _merge_within_source(base: MergeDict, override: MergeDict, *, at: MergeAt) -> MergeDict:
    """Merge *override* over *base* where both are parts of one source, keeping its deletes.

    :func:`_deep_merge` spends a delete on its base and drops it, which is right between two
    layers, where the base is everything below. Within one source, the base is only the part
    *override* refines: the layers the source is merged over later lie below both, so every
    delete either part holds stays in the result, at its path, to delete there too. One of
    *override* that removed a key of *base* is kept spent: it had its base, so no layer below
    need hold the key. One of *base* gives way to a value *override* writes at its key, and a
    dict written there keeps it as its base, cutting the layers below off as within one file
    (:func:`_written_over`). A delete below a node the merge made a list, or that a call, a
    union tag or a pin replaced, is not kept: that value replaces the layers below whole.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too
    """
    merged = _deep_merge(base, override, at=at)
    return _keep_deletes(merged, override, base, at)


def _keep_deletes(merged: MergeDict, override: MergeDict, base: MergeDict, at: MergeAt) -> MergeDict:
    """Return *merged* with each key delete *base* and *override* hold put back, at any depth.

    A delete of *override* that met a key of *base* is put back spent, any other as it was. A
    delete of *base* is put back where *override* says nothing at its key, and written over
    where it does. An override *at* reads as a value of its own discarded *base*, so nothing
    below it met one or survives.
    """
    if at.replaces(override):
        base = {}
    out = _with_base_deletes(dict(merged), override, base, at)
    values = {
        identity: [k for k in keys if not isinstance(base[k], _DeleteSentinel)]
        for identity, keys in _key_index(base, at).items()
    }
    for key, val in override.items():
        if isinstance(key, ListOp):
            continue
        if isinstance(val, _DeleteSentinel):
            out[key] = val if val is _SPENT_DELETE else _spent_if_met(base, key, at)
            continue
        met = values.get(at.key_identity(key))
        merged_key = met[-1] if met else key
        if isinstance(val, dict) and isinstance(out.get(merged_key), dict):
            below = base.get(merged_key)
            child = at.child(merged_key, base, override)
            if not isinstance(below, dict) or _replaces_what_lies_below(below, val, child):
                below = {}
            out[merged_key] = _keep_deletes(out[merged_key], val, below, child)
    return out


def _with_base_deletes(out: MergeDict, override: MergeDict, base: MergeDict, at: MergeAt) -> MergeDict:
    """Put each key delete of *base* back in *out*, or write *override*'s value at its key over it.

    The key *override* writes is any key *at* reads as the deleted one (:meth:`MergeAt.key_identity`).
    """
    written = _key_index(override, at)
    for key, val in base.items():
        if isinstance(val, _DeleteSentinel) and not isinstance(key, ListOp):
            over = written.get(at.key_identity(key), [])
            if not over:
                out[key] = val
            elif over[-1] in out:
                out[over[-1]] = _written_over(val, out[over[-1]])
    return out


def _without_key_deletes(node: Any) -> Any:
    """Return *node* with every delete it holds removed, at any depth; *node* itself when it holds none.

    For a value no layer lies below, an item of a list: a key delete kept for the layers below
    has nothing left to delete, and a deleted base (``{ListOp.BASE: DICT_DELETE}``) nothing to
    cut off.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too
    """
    if isinstance(node, list):
        items = [_without_key_deletes(v) for v in node]
        return items if any(new is not old for new, old in zip(items, node, strict=True)) else node
    if not isinstance(node, dict):
        return node
    kept = {k: _without_key_deletes(v) for k, v in node.items() if not isinstance(v, _DeleteSentinel)}
    return node if len(kept) == len(node) and all(kept[k] is v for k, v in node.items()) else kept


def _navigate_append_spec(d: MergeDict, part: str) -> MergeDict | None:
    """Return the appended item that a negative-index part points into, or None.

    Used when traversing a path through an active append-spec (a dict keyed by
    ListOp.APPEND). A negative index resolves to the corresponding appended
    item dict so that subsequent sub-field assignments patch it directly.
    """
    if ListOp.APPEND not in d:
        return None
    try:
        idx = int(part)
    except ValueError:
        return None
    if idx >= 0:
        return None
    items = d[ListOp.APPEND]
    if not isinstance(items, list):
        return None
    resolved = idx + len(items)
    if 0 <= resolved < len(items) and isinstance(items[resolved], dict):
        return items[resolved]
    return None


def _peek_nested(d: MergeDict, path: list[str], at: MergeAt | None = None) -> Any:
    """Return the value stored at *path*, or ``None`` when the path is not (fully) there.

    The read-only twin of :func:`_descend_creating`: it navigates append-specs the
    same way and stops at anything that is not a dict, so a caller can ask what
    ``_set_nested`` would have to descend through before it descends. Keep the two in step.

    Args:
        d: The root dict to read from.
        path: A list of keys forming the path to the target location.
        at: Where *d* stands, which reads each key's identity; the shape rule by default.

    Returns:
        The value at ``path``, or ``None`` if any segment is absent or not traversable.
    """
    node: Any = d
    at = at or MergeAt()
    for part in path:
        if not isinstance(node, dict):
            return None
        if (target := _navigate_append_spec(node, part)) is not None:
            node, at = target, at.child(part, node, None)
            continue
        key = _met_key(node, part, at)
        if key not in node:
            return None
        node, at = node[key], at.child(key, node, None)
    return node


def _set_nested(d: MergeDict, path: list[str], value: Any, at: MergeAt | None = None) -> None:
    """Set a value in a nested dict by following a list of keys.

    Intermediate nodes are opened by :func:`_open_for_ops`: a missing one is created, a
    plain list (from a prior full-replace CLI operation) becomes the
    ``{ListOp.BASE: list}`` base the later index patches are accumulated beside,
    and a whole-field delete becomes ``{ListOp.BASE: DICT_DELETE}``, so the ops
    below it still have nothing below them.  Any other non-dict intermediate is a scalar
    an earlier whole-value assignment left behind; a path cannot descend through it, so
    the deeper key replaces it (last write wins, as it already does when the two arrive
    from different sources).  A scalar that *means* something to its field is opened into
    that meaning before it gets here — see
    :func:`~confarg._parse_cli._open_callable_shorthand`.  The value itself is written by
    :func:`_written_over`, so a dict written over a whole-field delete keeps it as its base,
    and a delete written over a value an earlier write left is kept spent (:func:`_spent_if_met`).
    Each segment lands on the key the source already wrote that the type reads as the same
    key, whatever spelled it (:func:`_met_key`), so a later spelling writes over an earlier one.

    Args:
        d: The root dict to modify in place.
        path: A list of keys forming the path to the target location.
        value: The value to set at the target path.
        at: Where *d* stands, which reads each key's identity; the shape rule by default.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#scalar-intermediates
        docs-dev/architecture/pipeline/deep-merge.md#which-keys-are-one-key
    """
    if path:
        parent, at = _descend(d, path[:-1], at or MergeAt())
        key = _met_key(parent, path[-1], at)
        if value is DICT_DELETE:
            parent[key] = _spent_if_met(parent, key, at)
        else:
            parent[key] = _written_over(parent.get(key), value)


def _written_over(existing: Any, value: Any) -> Any:
    """Return what writing *value* where *existing* lies leaves there, both in one source.

    *value* itself, except a dict written over a whole-field delete: it keeps the delete
    as its base (:func:`_open_for_ops`), since a dict merges into the layers below where
    a list or a scalar replaces them.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it
    """
    if isinstance(value, dict) and isinstance(existing, _DeleteSentinel):
        return {**_open_for_ops(existing), **value}
    return value


def _open_for_ops(node: Any) -> MergeDict:
    """Return the dict an op recorded at or below a node writes into, given what *node* holds.

    A dict is written into as it is.  A plain list becomes the ``ListOp.BASE`` base the
    op is recorded beside, and a whole-field delete becomes a base of ``DICT_DELETE``:
    the op still applies to nothing below, the lower layers included.  Anything else -- a
    missing node, a scalar an earlier whole value left -- gives a fresh dict, the later
    writer winning.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it
    """
    if isinstance(node, dict):
        return node
    if isinstance(node, list):
        return {ListOp.BASE: node}
    if isinstance(node, _DeleteSentinel):
        return {ListOp.BASE: DICT_DELETE}
    return {}


def _descend_creating(d: MergeDict, path: list[str], at: MergeAt | None = None) -> MergeDict:
    """Return the dict at *path* inside *d*, opening every node on the way into one.

    The one descent every writer into a parse result shares, so an op recorded below a
    node treats what it finds there the same way whichever op it is: each node is opened
    by :func:`_open_for_ops`.

    Args:
        d: The root dict to modify in place.
        path: A list of keys forming the path to descend; empty returns *d*.
        at: Where *d* stands, which reads each key's identity; the shape rule by default.

    Returns:
        The dict now stored at *path*.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#scalar-intermediates
    """
    return _descend(d, path, at or MergeAt())[0]


def _descend(d: MergeDict, path: list[str], at: MergeAt) -> tuple[MergeDict, MergeAt]:
    """Return the dict at *path* inside *d* and where it stands, as :func:`_descend_creating` opens it."""
    for part in path:
        # Negative index into an active append-spec: navigate directly into the
        # appended item so multiple --field+ / --field.-1.sub sequences each
        # patch their own newly-added item rather than colliding on the "-N" key.
        if (target := _navigate_append_spec(d, part)) is not None:
            d, at = target, at.child(part, d, None)
            continue
        key = _met_key(d, part, at)
        child = at.child(key, d, None)
        d[key] = _open_for_ops(d.get(key))
        d, at = d[key], child
    return d, at


def _drop_deleted_bases(node: Any) -> Any:
    """Return *node* with every ``ListOp.BASE`` base of ``DICT_DELETE`` removed, at any depth.

    Run once every layer is merged: the deleted base has cut its ops off from the layers
    below, so what remains is the ops alone, which ``build()`` applies to nothing, as it
    does when no layer set the field.  A spent key delete no layer below met is removed
    too: it had its base in its own source.  Nodes holding neither are returned as they are.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it
        docs-dev/architecture/pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too
    """
    if isinstance(node, list):
        items = [_drop_deleted_bases(v) for v in node]
        return items if any(a is not b for a, b in zip(items, node, strict=True)) else node
    if not isinstance(node, dict):
        return node
    out = {k: _drop_deleted_bases(v) for k, v in node.items() if v is not _SPENT_DELETE}
    if out.get(ListOp.BASE) is DICT_DELETE:
        del out[ListOp.BASE]
    elif len(out) == len(node) and all(out[k] is node[k] for k in node):
        return node
    return out


def _accumulate_list_delete(  # noqa: PLR0913  # the node's place, the op and where the walk stands
    d: MergeDict,
    path: list[str],
    idx: int,
    source: str,
    *,
    delete_key: ListOp = ListOp.DELETE,
    at: MergeAt | None = None,
) -> None:
    """Add a list-deletion index at ``path`` inside ``d``, raising on duplicates.

    Args:
        d: The root data dict to modify in place.
        path: Path segments leading to the list field.
        idx: The (original) list index to delete.
        source: Human-readable description of the source (for error messages).
        delete_key: Which key to accumulate under — ListOp.DELETE for pre-append
            deletions, ListOp.DELETE_AFTER for deletions that follow an append.
        at: Where *d* stands, which reads each key's identity; the shape rule by default.

    Raises:
        ConfargError: If ``idx`` has already been scheduled for deletion.
    """
    node = _descend_creating(d, path, at)
    existing = node.get(delete_key)
    if isinstance(existing, list):
        if idx in existing:
            msg = f"Duplicate list-deletion index {idx} for {source!r}."
            raise ConfargError(msg)
        node[delete_key] = sorted([*existing, idx])
    else:
        node[delete_key] = [idx]

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Deep merge of the intermediate dicts, and the list/dict patch sentinels it understands.

Dev Notes:
    docs-dev/architecture/pipeline/deep-merge.md#deep-merge-semantics
"""

from __future__ import annotations

from typing import Any

from confarg import _defaults
from confarg.exceptions import ConfargError, TypeCoercionError


class _OpKey(str):
    """A key of the merged dict that records a list op rather than naming data.

    It reads as the reserved key a file writes the op with, so a message or a dump spells it
    the way a file does, but it equals only another marker of the same spelling: never the
    plain string, which any channel can type as a key of its own.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#no-channel-types-an-op
    """

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return type(other) is _OpKey and str.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash((_OpKey, str.__str__(self)))


# "Append these items to the list".  The value is a list or a scalar (single-value append);
# every producer stores one of those two shapes.
LIST_APPEND_KEY = _OpKey(_defaults.APPEND_KEY)

# "Delete these indices from the list".  The value is a sorted list of integers
# (original indices before deletion).
LIST_DELETE_KEY = _OpKey(_defaults.DELETE_KEY)

# "Replace the base with this value before applying the other operations".
# Produced when a whole-list value is followed by a patch or append; the value is the
# replacement list.  Also produced when a whole-field delete is followed by an op at or
# below its path; the value is then ``DICT_DELETE``: nothing lies below the ops.
LIST_REPLACE_BASE_KEY = _OpKey(_defaults.BASE_KEY)

# "Delete these indices AFTER appends have been applied".  Produced by the CLI parser when
# --field.N- appears after --field+.  The value is a sorted list of post-append indices.
LIST_POST_APPEND_DELETE_KEY = _OpKey(_defaults.DELETE_AFTER_KEY)

#: Every list op, keyed by the reserved key a file writes it with.
MERGE_OP_KEYS: dict[str, _OpKey] = {
    str(k): k for k in (LIST_APPEND_KEY, LIST_DELETE_KEY, LIST_REPLACE_BASE_KEY, LIST_POST_APPEND_DELETE_KEY)
}

# The suffixes a flag, a variable or a file key carries to append to the field it names
# (``--xs+``, ``xs+:``) or to delete it (``--d.k-``, ``k-:``, ``"0-":``).
APPEND_SUFFIX = "+"
DELETE_SUFFIX = "-"


class _DeleteSentinel:
    """Sentinel value indicating that a dict key should be removed during merge."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "_DELETE_"


# Singleton sentinel stored as a dict value to mark that key for deletion.
DICT_DELETE: _DeleteSentinel = _DeleteSentinel()


def _to_append_list(val: Any) -> list[Any]:
    """Convert the value stored under LIST_APPEND_KEY to a flat list of items.

    Every producer stores a list (or set/tuple) or a scalar; a dict never reaches
    here — the index-keyed dict form is a construct-time concern, handled in
    ``typedload._construct``, not an append value.
    """
    if isinstance(val, list | set | frozenset | tuple):
        return list(val)
    return [val]  # scalar single-value append


def _merge_regular_key(key: str, new_val: Any, result: dict[str, Any]) -> None:
    """Store new_val under key, preserving any existing append spec when new_val is a delete-spec."""
    prev = result.get(key)
    if isinstance(new_val, dict) and LIST_DELETE_KEY in new_val and isinstance(prev, dict) and LIST_APPEND_KEY in prev:
        result[key] = {**new_val, LIST_APPEND_KEY: prev[LIST_APPEND_KEY]}
    else:
        result[key] = _written_over(prev, new_val)


def _apply_append_key(plain_key: str, new_val: Any, result: dict[str, Any]) -> None:
    """Apply a ``key+`` shorthand entry, accumulating appends under ``plain_key``."""
    items = list(new_val) if isinstance(new_val, list) else [new_val]
    existing = result.get(plain_key)
    if isinstance(existing, list):
        result[plain_key] = existing + items
    elif isinstance(existing, dict) and LIST_APPEND_KEY in existing:
        result[plain_key] = {LIST_APPEND_KEY: existing[LIST_APPEND_KEY] + items}
    elif isinstance(existing, dict) and LIST_DELETE_KEY in existing:
        result[plain_key] = {**existing, LIST_APPEND_KEY: items}
    elif existing is DICT_DELETE:
        result[plain_key] = {**_open_for_ops(existing), LIST_APPEND_KEY: items}
    else:
        result[plain_key] = {LIST_APPEND_KEY: items}


def _normalize_merge_ops(d: Any) -> Any:
    """Recursively normalise ``key+`` / ``key-`` shorthand and the reserved op keys in file-sourced dicts.

    Transforms:
    - ``key+: val``        → ``key: {LIST_APPEND_KEY: list(val)}``   (append to list)
    - ``key-: val``        → ``key: DICT_DELETE``                    (remove dict key)
    - ``"N-": val``        → accumulated ``{LIST_DELETE_KEY: [N]}``  (delete list index N)
    - ``__append__: val`` and the other keys of ``MERGE_OP_KEYS`` → the op's marker

    Only dict keys are inspected; list items are left untouched.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#no-channel-types-an-op
    """
    if not isinstance(d, dict):
        return d

    has_change = False
    result: dict[str, Any] = {}
    delete_indices: list[int] = []

    for key, val in d.items():
        new_val = _normalize_merge_ops(val)
        if new_val is not val:
            has_change = True

        # A reserved key is stored as the marker of the op it spells (a marker equals none of
        # them), and a key that cannot carry a shorthand suffix is stored as it is.
        if key in MERGE_OP_KEYS or not isinstance(key, str) or isinstance(key, _OpKey) or len(key) <= 1:
            has_change = has_change or key in MERGE_OP_KEYS
            result[MERGE_OP_KEYS.get(key, key)] = new_val
            continue

        if key.endswith(APPEND_SUFFIX):
            has_change = True
            _apply_append_key(key[:-1], new_val, result)

        elif key.endswith(DELETE_SUFFIX):
            has_change = True
            plain_key = key[:-1]
            try:
                delete_indices.append(int(plain_key))
            except ValueError:
                result[plain_key] = DICT_DELETE

        else:
            # Regular key: preserve any append spec when overwriting with a delete-spec.
            _merge_regular_key(key, new_val, result)

    if delete_indices:
        existing_del = result.get(LIST_DELETE_KEY)
        if isinstance(existing_del, list):
            result[LIST_DELETE_KEY] = sorted(set(existing_del) | set(delete_indices))
        else:
            result[LIST_DELETE_KEY] = sorted(delete_indices)

    return result if has_change else d


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


def _replace_base(ops: dict[str, Any], key: str) -> list[Any]:
    """Return a copy of the base list *ops* carries under ``LIST_REPLACE_BASE_KEY``.

    The one reader of the key, for the merge and for construction alike: a value that is no
    list or tuple -- which only a file writing the key itself can hold -- is refused rather than
    read with ``list()``, which would split a string into its characters.

    Raises:
        TypeCoercionError: If the value is no list or tuple.
    """
    base = ops[LIST_REPLACE_BASE_KEY]
    if not isinstance(base, list | tuple):
        raise TypeCoercionError.op_not_a_list(LIST_REPLACE_BASE_KEY, "a list", type(base).__name__, base, key)
    return list(base)


def _delete_indices(ops: dict[str, Any], delete_key: str, key: str) -> list[int]:
    """Return the indices *ops* deletes under *delete_key*, ``LIST_DELETE_KEY`` or ``LIST_POST_APPEND_DELETE_KEY``.

    The one reader of the two keys: a value that is no list of integers -- which only a file
    writing the key itself can hold -- is refused rather than iterated.

    Raises:
        TypeCoercionError: If the value is no list or tuple of integers.
    """
    indices = ops[delete_key]
    if not isinstance(indices, list | tuple) or not all(type(i) is int for i in indices):
        raise TypeCoercionError.op_not_a_list(delete_key, "a list of indices", type(indices).__name__, indices, key)
    return list(indices)


def _apply_list_ops(
    working: list[Any],
    ops: dict[str, Any],
    key: str,
    union_tag: str | None,
) -> list[Any]:
    """Apply list mutation operations from *ops* onto *working* in order.

    Operations are applied in a fixed semantic order regardless of dict iteration:
    1. Pre-append deletions (LIST_DELETE_KEY): remove indices from *working*.
    2. Appends (LIST_APPEND_KEY): extend *working*.
    3. Post-append deletions (LIST_POST_APPEND_DELETE_KEY): remove indices
       from the post-append *working* (used when a CLI delete follows an append).
    4. Index patches (integer string keys, including negative): replace elements.

    LIST_REPLACE_BASE_KEY is ignored here; the caller already used it to set *working*.
    """
    # 1. Pre-append deletions
    if LIST_DELETE_KEY in ops:
        del_set = {_resolve_index(i, len(working), key, "delete") for i in _delete_indices(ops, LIST_DELETE_KEY, key)}
        working = [item for i, item in enumerate(working) if i not in del_set]

    # 2. Appends
    if LIST_APPEND_KEY in ops:
        working = working + _to_append_list(ops[LIST_APPEND_KEY])

    # 3. Post-append deletions
    if LIST_POST_APPEND_DELETE_KEY in ops:
        after = _delete_indices(ops, LIST_POST_APPEND_DELETE_KEY, key)
        del_set = {_resolve_index(i, len(working), key, "delete") for i in after}
        working = [item for i, item in enumerate(working) if i not in del_set]

    # 4. Index patches
    for ik, iv in ops.items():
        if isinstance(ik, _OpKey):
            continue
        try:
            orig_idx = int(ik)
        except ValueError:
            msg = (
                f"Cannot patch list '{key}' with non-integer key {ik!r}."
                " List patches must use integer string keys (e.g. {'0': ..., '1': ...})."
            )
            raise ConfargError(msg) from None
        idx = _resolve_index(orig_idx, len(working), key, "patch")
        working = list(working)  # ensure mutability
        # A list/tuple element + index-keyed dict recurses through _apply_list_ops, a dict
        # element + dict patch deep-merges, and anything else is replaced by iv.
        working[idx] = _merge_existing_value(working[idx], iv, key, union_tag)

    return working


def _patch_needs_the_type(base: list[Any], ops: dict[str, Any]) -> bool:
    """Whether *ops* is a pure patch whose meaning over *base* depends on the target type.

    A key that is no integer names a namedtuple field or nothing, and an index outside
    *base* fills a fixed tuple's slot or overruns a list. Such a patch is deferred to
    ``build()`` with the base carried along. Patches with append/delete keys return
    False so ``_apply_list_ops`` handles them (and raises its specific errors).

    Dev Notes:
        docs-dev/architecture/pipeline/merge-build-contract.md#merge-build-contract
    """
    if any(k in ops for k in (LIST_APPEND_KEY, LIST_DELETE_KEY, LIST_POST_APPEND_DELETE_KEY)):
        return False
    n = len(base)
    for k in ops:
        if k == LIST_REPLACE_BASE_KEY:
            continue
        try:
            i = int(k)
        except (TypeError, ValueError):
            return True
        if not -n <= i < n:
            return True
    return False


def _merge_existing_value(bv: Any, val: Any, key: str, union_tag: str | None) -> Any:
    """Compute the merged value when *key* exists in both base and override.

    An override carrying its own base (``LIST_REPLACE_BASE_KEY``) replaces a dict base
    outright, as a union tag does: the patches beside that base address it, not whatever
    an earlier layer held.  A base that is a whole-field delete replaces a list base too.
    A dict's own key ``'*'`` is no base, whatever it holds: no channel spells the marker.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#deep-merge-semantics
    """
    if (
        isinstance(val, dict)
        and LIST_REPLACE_BASE_KEY in val
        and (val[LIST_REPLACE_BASE_KEY] is DICT_DELETE or isinstance(bv, dict))
    ):
        return val
    if isinstance(bv, dict) and isinstance(val, dict):
        if LIST_APPEND_KEY in bv and LIST_APPEND_KEY in val:
            combined = _to_append_list(bv[LIST_APPEND_KEY]) + _to_append_list(val[LIST_APPEND_KEY])
            rest = _deep_merge(
                {k: v for k, v in bv.items() if k != LIST_APPEND_KEY},
                {k: v for k, v in val.items() if k != LIST_APPEND_KEY},
                union_tag=union_tag,
            )
            return {**rest, LIST_APPEND_KEY: combined}
        if LIST_DELETE_KEY in bv and LIST_DELETE_KEY in val:
            combined_del = sorted(
                set(_delete_indices(bv, LIST_DELETE_KEY, key)) | set(_delete_indices(val, LIST_DELETE_KEY, key)),
            )
            rest = _deep_merge(
                {k: v for k, v in bv.items() if k != LIST_DELETE_KEY},
                {k: v for k, v in val.items() if k != LIST_DELETE_KEY},
                union_tag=union_tag,
            )
            return {**rest, LIST_DELETE_KEY: combined_del}
        return _deep_merge(bv, val, union_tag=union_tag)
    if isinstance(bv, list) and isinstance(val, dict):
        return _merge_list_base(bv, val, key, union_tag)
    return val


def _merge_list_base(bv: list[Any], val: dict[str, Any], key: str, union_tag: str | None) -> Any:
    """Combine a list base *bv* with an override patch dict *val*."""
    if LIST_REPLACE_BASE_KEY in val:
        return _apply_list_ops(_replace_base(val, key), val, key, union_tag)
    if _patch_needs_the_type(bv, val):
        # Defer to build(): an out-of-range index is an error for a list, a slot for a tuple;
        # a name key is an error for a list, a field for a namedtuple.
        return {LIST_REPLACE_BASE_KEY: list(bv), **val}
    return _apply_list_ops(list(bv), val, key, union_tag)


def _deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
    *,
    union_tag: str | None = None,
) -> dict[str, Any]:
    """Recursively merge override into base, with override winning on conflict.

    Dict values are merged recursively.  Special override values:

    - ``DICT_DELETE`` as a value → removes that key from the result.
    - ``{LIST_REPLACE_BASE_KEY: list}`` as a value for a list base → replaces the base
      list, then applies any additional append, delete or integer-key operations.
    - ``{LIST_APPEND_KEY: items}`` as a value for a list base → appends items.
    - ``{LIST_DELETE_KEY: [i, j]}`` as a value for a list base → deletes original indices i, j.
    - ``{"N": v}`` (integer string keys) as a value for a list base → patches by index.

    When ``union_tag`` is set and the override dict contains that key, the override
    is treated as a fresh object specification and the base is discarded entirely.

    Args:
        base: The base dict to merge into.
        override: The dict whose values take precedence.
        union_tag: The discriminator key used for union disambiguation.

    Returns:
        A new dict containing the merged result.

    Raises:
        ConfargError: If a delete index is out of range, or if a list patch beside an
            append or a delete uses an out-of-range index or a non-integer key.
    """
    base = _normalize_merge_ops(base)
    override = _normalize_merge_ops(override)

    if union_tag is not None and union_tag in override:
        return dict(override)

    # Copy base, skipping any DICT_DELETE sentinels left over from normalization -- but not
    # a deleted base, which still cuts its node off from the layers merged under it later.
    result = {k: v for k, v in base.items() if k == LIST_REPLACE_BASE_KEY or not isinstance(v, _DeleteSentinel)}

    for key, val in override.items():
        if isinstance(val, _DeleteSentinel):
            result.pop(key, None)
        elif key in result:
            result[key] = _merge_existing_value(result[key], val, key, union_tag)
        else:
            result[key] = val
    return result


def _navigate_append_spec(d: dict[str, Any], part: str) -> dict[str, Any] | None:
    """Return the appended item that a negative-index part points into, or None.

    Used when traversing a path through an active append-spec (a dict keyed by
    LIST_APPEND_KEY). A negative index resolves to the corresponding appended
    item dict so that subsequent sub-field assignments patch it directly.
    """
    if LIST_APPEND_KEY not in d:
        return None
    try:
        idx = int(part)
    except ValueError:
        return None
    if idx >= 0:
        return None
    items = d[LIST_APPEND_KEY]
    if not isinstance(items, list):
        return None
    resolved = idx + len(items)
    if 0 <= resolved < len(items) and isinstance(items[resolved], dict):
        return items[resolved]
    return None


def _peek_nested(d: dict[str, Any], path: list[str]) -> Any:
    """Return the value stored at *path*, or ``None`` when the path is not (fully) there.

    The read-only twin of :func:`_descend_creating`: it navigates append-specs the
    same way and stops at anything that is not a dict, so a caller can ask what
    ``_set_nested`` would have to descend through before it descends. Keep the two in step.

    Args:
        d: The root dict to read from.
        path: A list of keys forming the path to the target location.

    Returns:
        The value at ``path``, or ``None`` if any segment is absent or not traversable.
    """
    node: Any = d
    for part in path:
        if not isinstance(node, dict):
            return None
        if (target := _navigate_append_spec(node, part)) is not None:
            node = target
            continue
        if part not in node:
            return None
        node = node[part]
    return node


def _set_nested(d: dict[str, Any], path: list[str], value: Any) -> None:
    """Set a value in a nested dict by following a list of keys.

    Intermediate nodes are opened by :func:`_open_for_ops`: a missing one is created, a
    plain list (from a prior full-replace CLI operation) becomes the
    ``{LIST_REPLACE_BASE_KEY: list}`` base the later index patches are accumulated beside,
    and a whole-field delete becomes ``{LIST_REPLACE_BASE_KEY: DICT_DELETE}``, so the ops
    below it still have nothing below them.  Any other non-dict intermediate is a scalar
    an earlier whole-value assignment left behind; a path cannot descend through it, so
    the deeper key replaces it (last write wins, as it already does when the two arrive
    from different sources).  A scalar that *means* something to its field is opened into
    that meaning before it gets here — see
    :func:`~confarg._parse_cli._open_callable_shorthand`.  The value itself is written by
    :func:`_written_over`, so a dict written over a whole-field delete keeps it as its base.

    Args:
        d: The root dict to modify in place.
        path: A list of keys forming the path to the target location.
        value: The value to set at the target path.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#scalar-intermediates
    """
    if path:
        parent = _descend_creating(d, path[:-1])
        parent[path[-1]] = _written_over(parent.get(path[-1]), value)


def _written_over(existing: Any, value: Any) -> Any:
    """Return what writing *value* where *existing* lies leaves there, both in one source.

    *value* itself, except a dict written over a whole-field delete: it keeps the delete
    as its base (:func:`_open_for_ops`), since a dict merges into the layers below where
    a list or a scalar replaces them.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it
    """
    if isinstance(value, dict) and existing is DICT_DELETE:
        return {**_open_for_ops(existing), **value}
    return value


def _open_for_ops(node: Any) -> dict[str, Any]:
    """Return the dict an op recorded at or below a node writes into, given what *node* holds.

    A dict is written into as it is.  A plain list becomes the ``LIST_REPLACE_BASE_KEY`` base the
    op is recorded beside, and a whole-field delete becomes a base of ``DICT_DELETE``:
    the op still applies to nothing below, the lower layers included.  Anything else -- a
    missing node, a scalar an earlier whole value left -- gives a fresh dict, the later
    writer winning.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it
    """
    if isinstance(node, dict):
        return node
    if isinstance(node, list) or node is DICT_DELETE:
        return {LIST_REPLACE_BASE_KEY: node}
    return {}


def _descend_creating(d: dict[str, Any], path: list[str]) -> dict[str, Any]:
    """Return the dict at *path* inside *d*, opening every node on the way into one.

    The one descent every writer into a parse result shares, so an op recorded below a
    node treats what it finds there the same way whichever op it is: each node is opened
    by :func:`_open_for_ops`.

    Args:
        d: The root dict to modify in place.
        path: A list of keys forming the path to descend; empty returns *d*.

    Returns:
        The dict now stored at *path*.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#scalar-intermediates
    """
    for part in path:
        # Negative index into an active append-spec: navigate directly into the
        # appended item so multiple --field+ / --field.-1.sub sequences each
        # patch their own newly-added item rather than colliding on the "-N" key.
        if (target := _navigate_append_spec(d, part)) is not None:
            d = target
            continue
        d[part] = _open_for_ops(d.get(part))
        d = d[part]
    return d


def _drop_deleted_bases(node: Any) -> Any:
    """Return *node* with every ``LIST_REPLACE_BASE_KEY`` base of ``DICT_DELETE`` removed, at any depth.

    Run once every layer is merged: the deleted base has cut its ops off from the layers
    below, so what remains is the ops alone, which ``build()`` applies to nothing, as it
    does when no layer set the field.  Nodes holding none are returned as they are.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it
    """
    if isinstance(node, list):
        items = [_drop_deleted_bases(v) for v in node]
        return items if any(a is not b for a, b in zip(items, node, strict=True)) else node
    if not isinstance(node, dict):
        return node
    out = {k: _drop_deleted_bases(v) for k, v in node.items()}
    if out.get(LIST_REPLACE_BASE_KEY) is DICT_DELETE:
        del out[LIST_REPLACE_BASE_KEY]
    elif all(out[k] is node[k] for k in node):
        return node
    return out


def _accumulate_list_delete(
    d: dict[str, Any],
    path: list[str],
    idx: int,
    source: str,
    delete_key: str = LIST_DELETE_KEY,
) -> None:
    """Add a list-deletion index at ``path`` inside ``d``, raising on duplicates.

    Args:
        d: The root data dict to modify in place.
        path: Path segments leading to the list field.
        idx: The (original) list index to delete.
        source: Human-readable description of the source (for error messages).
        delete_key: Which key to accumulate under — LIST_DELETE_KEY for pre-append
            deletions, LIST_POST_APPEND_DELETE_KEY for deletions that follow an append.

    Raises:
        ConfargError: If ``idx`` has already been scheduled for deletion.
    """
    node = _descend_creating(d, path)
    existing = node.get(delete_key)
    if isinstance(existing, list):
        if idx in existing:
            msg = f"Duplicate list-deletion index {idx} for {source!r}."
            raise ConfargError(msg)
        node[delete_key] = sorted([*existing, idx])
    else:
        node[delete_key] = [idx]

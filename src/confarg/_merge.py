# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Deep merge and nested dict utilities for confarg."""

from __future__ import annotations

from typing import Any

from confarg.exceptions import ConfargError

# Special key used in the intermediate dict to signal "append these items to the list".
# The value may be a list (from CLI), a scalar (single-value append), or a dict with
# integer string keys (from future env-var support).
LIST_APPEND_KEY = "+"

# Special key used in the intermediate dict to signal "delete these indices from the list".
# The value is a sorted list of integers (original indices before deletion).
LIST_DELETE_KEY = "-"

# Special key used in the intermediate dict to signal "replace the base list with this
# value before applying other operations".  Produced by the CLI parser when a full-replace
# (--field or --field val…) is followed by a patch/append so that the replace is not lost
# during merge.  The value is the replacement list.
LIST_REPLACE_BASE_KEY = "*"

# Special key used in the intermediate dict to signal "delete these indices from the list
# AFTER appends have been applied".  Produced by the CLI parser when --field.N- appears
# after --field+ in the argument list, so the index refers to the post-append list.
# The value is a sorted list of integers (original post-append indices).
LIST_POST_APPEND_DELETE_KEY = "~"


class _DeleteSentinel:
    """Sentinel value indicating that a dict key should be removed during merge."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "_DELETE_"


# Singleton sentinel stored as a dict value to mark that key for deletion.
DICT_DELETE: _DeleteSentinel = _DeleteSentinel()


def _to_append_list(val: Any) -> list[Any]:
    """Convert the value stored under LIST_APPEND_KEY to a flat list of items."""
    if isinstance(val, list | set | frozenset | tuple):
        return list(val)
    if isinstance(val, dict):
        if not val:
            return []
        try:
            max_idx = max(int(k) for k in val)
        except ValueError:
            msg = f"Append dict keys must be integer indices, got: {sorted(val.keys())!r}"
            raise ConfargError(msg) from None
        return [val.get(str(i)) for i in range(max_idx + 1)]
    return [val]  # scalar single-value append


def _merge_regular_key(key: str, new_val: Any, result: dict[str, Any]) -> None:
    """Store new_val under key, preserving any existing append spec when new_val is a delete-spec."""
    prev = result.get(key)
    if isinstance(new_val, dict) and LIST_DELETE_KEY in new_val and isinstance(prev, dict) and LIST_APPEND_KEY in prev:
        result[key] = {**new_val, LIST_APPEND_KEY: prev[LIST_APPEND_KEY]}
    else:
        result[key] = new_val


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
    else:
        result[plain_key] = {LIST_APPEND_KEY: items}


def _normalize_merge_ops(d: Any) -> Any:
    """Recursively normalise ``key+`` / ``key-`` shorthand in file-sourced dicts.

    Transforms:
    - ``key+: val``        → ``key: {"+": list(val)}``   (append to list)
    - ``key-: val``        → ``key: DICT_DELETE``         (remove dict key)
    - ``"N-": val``        → accumulated ``{"-": [N]}``   (delete list index N)

    Only dict keys are inspected; list items are left untouched.
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

        if not isinstance(key, str) or len(key) <= 1:
            result[key] = new_val
            continue

        if key.endswith("+"):
            has_change = True
            _apply_append_key(key[:-1], new_val, result)

        elif key.endswith("-"):
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


def _apply_list_ops(
    working: list[Any],
    ops: dict[str, Any],
    key: str,
    union_tag: str | None,
) -> list[Any]:
    """Apply list mutation operations from *ops* onto *working* in order.

    Operations are applied in a fixed semantic order regardless of dict iteration:
    1. Pre-append deletions (LIST_DELETE_KEY ``"-"``): remove indices from *working*.
    2. Appends (LIST_APPEND_KEY ``"+"``): extend *working*.
    3. Post-append deletions (LIST_POST_APPEND_DELETE_KEY ``"~"``): remove indices
       from the post-append *working* (used when a CLI delete follows an append).
    4. Index patches (integer string keys, including negative): replace elements.

    LIST_REPLACE_BASE_KEY (``"*"``) is ignored here; the caller already used it
    to set *working*.
    """

    def _check_del(orig_idx: int, lst: list[Any]) -> int:
        idx = orig_idx + len(lst) if orig_idx < 0 else orig_idx
        if idx < 0 or idx >= len(lst):
            _rng = "(the list is empty)" if not lst else f"(valid indices {-len(lst)} to {len(lst) - 1})"
            msg = f"Cannot delete index {orig_idx} from '{key}': the list has {len(lst)} element(s) {_rng}."
            raise ConfargError(msg)
        return idx

    # 1. Pre-append deletions
    if LIST_DELETE_KEY in ops:
        del_set = {_check_del(i, working) for i in ops[LIST_DELETE_KEY]}
        working = [item for i, item in enumerate(working) if i not in del_set]

    # 2. Appends
    if LIST_APPEND_KEY in ops:
        working = working + _to_append_list(ops[LIST_APPEND_KEY])

    # 3. Post-append deletions
    if LIST_POST_APPEND_DELETE_KEY in ops:
        del_set = {_check_del(i, working) for i in ops[LIST_POST_APPEND_DELETE_KEY]}
        working = [item for i, item in enumerate(working) if i not in del_set]

    # 4. Index patches
    _SKIP = {LIST_REPLACE_BASE_KEY, LIST_DELETE_KEY, LIST_APPEND_KEY, LIST_POST_APPEND_DELETE_KEY}
    for ik, iv in ops.items():
        if ik in _SKIP:
            continue
        try:
            orig_idx = int(ik)
        except ValueError:
            msg = (
                f"Cannot patch list '{key}' with non-integer key {ik!r}."
                " List patches must use integer string keys (e.g. {'0': ..., '1': ...})."
            )
            raise ConfargError(msg) from None
        idx = orig_idx + len(working) if orig_idx < 0 else orig_idx
        if idx < 0 or idx >= len(working):
            _rng = "(the list is empty)" if not working else f"(valid indices {-len(working)} to {len(working) - 1})"
            msg = (
                f"Cannot patch list '{key}' at index {orig_idx}:"
                f" the list has {len(working)} element(s) {_rng}."
                " Use the + append syntax (e.g. --field+ for CLI) to add new elements."
            )
            raise ConfargError(msg)
        working = list(working)  # ensure mutability
        working[idx] = (
            _deep_merge(working[idx], iv, union_tag=union_tag)
            if isinstance(working[idx], dict) and isinstance(iv, dict)
            else iv
        )

    return working


def _merge_existing_value(bv: Any, val: Any, key: str, union_tag: str | None) -> Any:
    """Compute the merged value when *key* exists in both base and override."""
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
            combined_del = sorted(set(bv[LIST_DELETE_KEY]) | set(val[LIST_DELETE_KEY]))
            rest = _deep_merge(
                {k: v for k, v in bv.items() if k != LIST_DELETE_KEY},
                {k: v for k, v in val.items() if k != LIST_DELETE_KEY},
                union_tag=union_tag,
            )
            return {**rest, LIST_DELETE_KEY: combined_del}
        return _deep_merge(bv, val, union_tag=union_tag)
    if isinstance(bv, list) and isinstance(val, dict):
        if LIST_REPLACE_BASE_KEY in val:
            return _apply_list_ops(list(val[LIST_REPLACE_BASE_KEY]), val, key, union_tag)
        return _apply_list_ops(list(bv), val, key, union_tag)
    return val


def _deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
    *,
    union_tag: str | None = None,
) -> dict[str, Any]:
    """Recursively merge override into base, with override winning on conflict.

    Dict values are merged recursively.  Special override values:

    - ``DICT_DELETE`` as a value → removes that key from the result.
    - ``{"*": list}`` as a value for a list base → replaces the base list, then
      applies any additional ``"+"``, ``"-"``, or integer-key operations.
    - ``{"+": items}`` as a value for a list base → appends items.
    - ``{"-": [i, j]}`` as a value for a list base → deletes original indices i, j.
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
        ConfargError: If a list is patched/deleted with an out-of-range index, or
            if a non-integer key is used for list patching.
    """
    base = _normalize_merge_ops(base)
    override = _normalize_merge_ops(override)

    if union_tag is not None and union_tag in override:
        return dict(override)

    # Copy base, skipping any DICT_DELETE sentinels left over from normalization.
    result = {k: v for k, v in base.items() if not isinstance(v, _DeleteSentinel)}

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


def _set_nested(d: dict[str, Any], path: list[str], value: Any) -> None:
    """Set a value in a nested dict by following a list of keys.

    Intermediate dicts are created as needed.  If an intermediate value is a
    plain list (from a prior full-replace CLI operation), it is converted to
    ``{LIST_REPLACE_BASE_KEY: list}`` so that subsequent index patches can be
    accumulated alongside it.

    Args:
        d: The root dict to modify in place.
        path: A list of keys forming the path to the target location.
        value: The value to set at the target path.
    """
    for part in path[:-1]:
        # Negative index into an active append-spec: navigate directly into the
        # appended item so multiple --field+ / --field.-1.sub sequences each
        # patch their own newly-added item rather than colliding on the "-N" key.
        if isinstance(d, dict) and (target := _navigate_append_spec(d, part)) is not None:
            d = target
            continue
        if part not in d:
            d[part] = {}
        elif isinstance(d[part], list):
            d[part] = {LIST_REPLACE_BASE_KEY: d[part]}
        d = d[part]
    if path:
        d[path[-1]] = value


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
    node = d
    for key in path:
        if key not in node:
            node[key] = {}
        elif isinstance(node[key], list):
            node[key] = {LIST_REPLACE_BASE_KEY: node[key]}
        node = node[key]
    existing = node.get(delete_key)
    if isinstance(existing, list):
        if idx in existing:
            msg = f"Duplicate list-deletion index {idx} for {source!r}."
            raise ConfargError(msg)
        node[delete_key] = sorted([*existing, idx])
    else:
        node[delete_key] = [idx]

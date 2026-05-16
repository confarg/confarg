# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Deep merge and nested dict utilities for confarg."""

from __future__ import annotations

from typing import Any

from confarg._errors import ConfargError

# Special key used in the intermediate dict to signal "append these items to the list".
# The value may be a list (from CLI), a scalar (single-value append), or a dict with
# integer string keys (from future env-var support).
LIST_APPEND_KEY = "+"

# Special key used in the intermediate dict to signal "delete these indices from the list".
# The value is a sorted list of non-negative integers (original indices before deletion).
LIST_DELETE_KEY = "-"


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
            raise ConfargError(f"Append dict keys must be integer indices, got: {sorted(val.keys())!r}") from None
        return [val.get(str(i)) for i in range(max_idx + 1)]
    return [val]  # scalar single-value append


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
            plain_key = key[:-1]
            items = list(new_val) if isinstance(new_val, list) else [new_val]
            existing = result.get(plain_key)
            if isinstance(existing, list):
                result[plain_key] = existing + items
            elif isinstance(existing, dict) and LIST_APPEND_KEY in existing:
                result[plain_key] = {LIST_APPEND_KEY: existing[LIST_APPEND_KEY] + items}
            elif isinstance(existing, dict) and LIST_DELETE_KEY in existing:
                # key already produced a delete spec; add the append spec alongside it
                result[plain_key] = {**existing, LIST_APPEND_KEY: items}
            else:
                result[plain_key] = {LIST_APPEND_KEY: items}

        elif key.endswith("-"):
            has_change = True
            plain_key = key[:-1]
            try:
                delete_indices.append(int(plain_key))
            except ValueError:
                result[plain_key] = DICT_DELETE

        else:
            # Regular key: if new_val is a delete-spec dict and a prior key+ already set an
            # append spec here, preserve the append spec rather than overwriting it.
            prev = result.get(key)
            if (
                isinstance(new_val, dict)
                and LIST_DELETE_KEY in new_val
                and isinstance(prev, dict)
                and LIST_APPEND_KEY in prev
            ):
                result[key] = {**new_val, LIST_APPEND_KEY: prev[LIST_APPEND_KEY]}
            else:
                result[key] = new_val

    if delete_indices:
        existing_del = result.get(LIST_DELETE_KEY)
        if isinstance(existing_del, list):
            result[LIST_DELETE_KEY] = sorted(set(existing_del) | set(delete_indices))
        else:
            result[LIST_DELETE_KEY] = sorted(delete_indices)

    return result if has_change else d


def _deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
    *,
    union_tag: str | None = None,
) -> dict[str, Any]:
    """Recursively merge override into base, with override winning on conflict.

    Dict values are merged recursively.  Special override values:

    - ``DICT_DELETE`` as a value → removes that key from the result.
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
        # Dict-key deletion: remove from result regardless of base value.
        if isinstance(val, _DeleteSentinel):
            result.pop(key, None)
            continue

        if key in result:
            bv = result[key]
            if isinstance(bv, dict) and isinstance(val, dict):
                # Both sides carry append entries → concatenate.
                if LIST_APPEND_KEY in bv and LIST_APPEND_KEY in val:
                    combined = _to_append_list(bv[LIST_APPEND_KEY]) + _to_append_list(val[LIST_APPEND_KEY])
                    rest = _deep_merge(
                        {k: v for k, v in bv.items() if k != LIST_APPEND_KEY},
                        {k: v for k, v in val.items() if k != LIST_APPEND_KEY},
                        union_tag=union_tag,
                    )
                    result[key] = {**rest, LIST_APPEND_KEY: combined}
                # Both sides carry delete entries → union the index sets.
                elif LIST_DELETE_KEY in bv and LIST_DELETE_KEY in val:
                    combined_del = sorted(set(bv[LIST_DELETE_KEY]) | set(val[LIST_DELETE_KEY]))
                    rest = _deep_merge(
                        {k: v for k, v in bv.items() if k != LIST_DELETE_KEY},
                        {k: v for k, v in val.items() if k != LIST_DELETE_KEY},
                        union_tag=union_tag,
                    )
                    result[key] = {**rest, LIST_DELETE_KEY: combined_del}
                else:
                    result[key] = _deep_merge(bv, val, union_tag=union_tag)

            elif isinstance(bv, list) and isinstance(val, dict):
                if LIST_DELETE_KEY in val:
                    del_indices = val[LIST_DELETE_KEY]
                    for idx in del_indices:
                        if idx < 0 or idx >= len(bv):
                            raise ConfargError(
                                f"Cannot delete index {idx} from '{key}':"
                                f" the list has {len(bv)} element(s)"
                                f" (valid indices 0-{len(bv) - 1})."
                            )
                    del_set = set(del_indices)
                    current = [item for i, item in enumerate(bv) if i not in del_set]
                    if LIST_APPEND_KEY in val:
                        result[key] = current + _to_append_list(val[LIST_APPEND_KEY])
                    else:
                        result[key] = current
                elif LIST_APPEND_KEY in val:
                    result[key] = list(bv) + _to_append_list(val[LIST_APPEND_KEY])
                else:
                    patched = list(bv)
                    for ik, iv in val.items():
                        try:
                            idx = int(ik)
                        except ValueError:
                            raise ConfargError(
                                f"Cannot patch list '{key}' with non-integer key {ik!r}."
                                " List patches must use integer string keys (e.g. {'0': ..., '1': ...})."
                            ) from None
                        if idx < 0:
                            raise ConfargError(f"Cannot patch list '{key}' with negative index {idx}")
                        if idx >= len(patched):
                            raise ConfargError(
                                f"Cannot extend list '{key}' at index {idx}:"
                                f" the list has {len(patched)} element(s)"
                                f" (valid indices 0-{len(patched) - 1})."
                                " Use the + append syntax (e.g. --field+ for CLI) to add new elements."
                            )
                        patched[idx] = (
                            _deep_merge(patched[idx], iv, union_tag=union_tag)
                            if isinstance(patched[idx], dict) and isinstance(iv, dict)
                            else iv
                        )
                    result[key] = patched
            else:
                result[key] = val
        else:
            result[key] = val
    return result


def _set_nested(d: dict[str, Any], path: list[str], value: Any) -> None:
    """Set a value in a nested dict by following a list of keys.

    Intermediate dicts are created as needed.

    Args:
        d: The root dict to modify in place.
        path: A list of keys forming the path to the target location.
        value: The value to set at the target path.
    """
    for part in path[:-1]:
        if part not in d:
            d[part] = {}
        d = d[part]
    if path:
        d[path[-1]] = value


def _accumulate_list_delete(d: dict[str, Any], path: list[str], idx: int, source: str) -> None:
    """Add a list-deletion index at ``path`` inside ``d``, raising on duplicates.

    Args:
        d: The root data dict to modify in place.
        path: Path segments leading to the list field.
        idx: The (original) list index to delete.
        source: Human-readable description of the source (for error messages).

    Raises:
        ConfargError: If ``idx`` has already been scheduled for deletion.
    """
    node = d
    for key in path:
        if key not in node:
            node[key] = {}
        node = node[key]
    existing = node.get(LIST_DELETE_KEY)
    if isinstance(existing, list):
        if idx in existing:
            raise ConfargError(f"Duplicate list-deletion index {idx} for {source!r}.")
        node[LIST_DELETE_KEY] = sorted(existing + [idx])
    else:
        node[LIST_DELETE_KEY] = [idx]

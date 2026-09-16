# REF-21 — `_construct_sequence` / `_construct_list` / `_construct_set` are three thin wrappers

**Where:** `src/confarg/typedload/_construct.py` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** none

`_construct_sequence` (line 189) just dispatches `_is_list` → `_construct_list`, else
`_construct_set`; both leaf functions are thin wrappers over `_build_items` — one returns the list,
the other `set(...)` / `frozenset(...)`. Fold all three into one `_construct_collection(tp, data,
path, union_tag)` that calls `_build_items` and wraps the result with the right constructor from
`_origin(tp)`. Removes two one-line functions and the dispatch indirection.

# REF-2 — The scalar-cast table exists three times

**Where:** `_cast.SCALAR_CAST_TYPES`, `typedload/_construct._CAST_TYPE_NAMES`,
`cli/argparse/_build._SCALAR_CAST_TYPES` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** medium · **Impact:** none

Three copies of the same list of castable scalar types, one per call site. `_cast` should own
it and the other two should import it — a new cast type currently has to be added in three
places to work everywhere. See [09-invariants.md](../../architecture/09-invariants.md).

`_cast` now also derives the reverse map, `cast_name_for_type`, which names a `_Pinned` on the
way out; `_construct._CAST_TYPE_NAMES` is the copy that reads that name back, so folding it in
is what keeps the writer and the reader on one table.

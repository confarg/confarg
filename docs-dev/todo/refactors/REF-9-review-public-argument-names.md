# REF-9 — Review public argument names and order

**Where:** `src/confarg/_api.py`, `src/confarg/cli/*/` · **Filed:** 2026-09-12
**Effort:** L · **Risk:** medium · **Impact:** api

The keyword sets of `load` / `merge` / `build` and the three adapter triads grew one feature at
a time. Review names and ordering once, while the library is not shipping and breaking changes
are free. See [pipeline/api-seams.md#public-api-seams](../../architecture/pipeline/api-seams.md#public-api-seams).

The shared source keywords are now declared once, as `MergeOptions` in `src/confarg/_defaults.py`
([api-seams](../../architecture/pipeline/api-seams.md#one-option-set)), so renaming one of them is
a change to that TypedDict and its callers, not to fourteen signatures.

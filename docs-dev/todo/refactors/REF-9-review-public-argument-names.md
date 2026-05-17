# REF-9 — Review public argument names and order

**Where:** `src/confarg/_api.py`, `src/confarg/cli/*/` · **Filed:** 2026-09-12
**Effort:** L · **Risk:** medium · **Impact:** api

The keyword sets of `load` / `merge` / `build` and the three adapter triads grew one feature at
a time. Review names and ordering once, while the library is not shipping and breaking changes
are free. See [01-pipeline-and-contracts.md#public-api-seams](../../architecture/01-pipeline-and-contracts.md#public-api-seams).

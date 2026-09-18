# REF-31 — `_missing_field_error` is defined twice

**Where:** `src/confarg/typedload/_construct.py` · **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

`_missing_field_error` is defined twice at module level (lines 74 and 86),
identically. The second definition silently shadows the first, so the first
is dead code. Delete the first; nothing changes. Link:
[09-invariants.md#delegate-to-the-canonical-function](../../architecture/09-invariants.md#delegate-to-the-canonical-function)
names `_missing_field_error` as the canonical error for a missing field.

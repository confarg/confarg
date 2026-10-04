# REF-74 — Scalar-cast registration mirrors the collector's dispatch by hand

**Where:** `src/confarg/cli/_build.py` (`_scalar_cast_parent_is_leaf`) ·
`src/confarg/cli/_collect.py` (`_collect_field`) · **Filed:** 2026-10-01
**Effort:** S · **Risk:** medium · **Impact:** none

BUG-72 registers a typed scalar cast (`--host.str`) only when its parent reaches the leaf
branch of `_collect_field`, because that is the branch that reads the cast. The predicate says
it "mirrors the collector's dispatch". It does this by listing, in a separate `not (... or ...)`
chain, every branch that comes before the leaf branch. Adding or reordering a branch in
`_collect_field` silently splits the two: the framework would then accept a flag the collector
drops, or refuse one it would read. Fix direction: give `_collect_field`'s dispatch a named
`_field_kind(resolved)` (or share REF-47's `_type_kind`), and have both sites ask it. See
[invariants.md#delegate-to-the-canonical-function](../../architecture/invariants.md#delegate-to-the-canonical-function).

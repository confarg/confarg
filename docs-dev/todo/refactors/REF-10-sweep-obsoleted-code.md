# REF-10 — Sweep for code obsoleted by past refactors

**Where:** `src/confarg/` · **Filed:** 2026-09-12
**Effort:** M · **Risk:** high · **Impact:** none

Helpers, branches and parameters kept alive by a single caller that a later refactor made
redundant. Worth one deliberate pass with coverage data rather than opportunistic deletions.

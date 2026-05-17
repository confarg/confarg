# REF-6 — `LIST_APPEND_KEY` accepts a value nothing produces

**Where:** `src/confarg/_merge.py` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** high · **Impact:** none

The index-keyed dict branch was added "for future env-var support" that never arrived. Either
wire up the env path or drop the branch; untested speculative code in the merge core is worse
than neither.

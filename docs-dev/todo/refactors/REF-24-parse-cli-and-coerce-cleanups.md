# REF-24 — Minor cleanups in `_parse_cli` and `_coerce`

**Where:** `src/confarg/_parse_cli.py`, `src/confarg/typedload/_coerce.py` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** none

Grab-bag of small, low-risk tidyings found while analyzing the two modules:

1. `_looks_like_flag` (lines 360-365) uses a `_double_dash = "--"` local plus `len(_double_dash)`
   indexing; clearer as a `len(token) > 2 and (token[2].isalpha() or token[2] == "_")` one-liner.
2. `_coerce_leaf` (line 251) and `_try_coerce` (line 291) keep parallel "is this coercible" predicates
   (`_is_literal or _is_enum or ft in (bool, int, float) or ft in _LEAF_COERCIONS or _is_none_type`).
   A single `_is_eagerly_coercible(tp)` predicate would keep them aligned. Lower priority — the two
   diverge intentionally on raise-vs-return, so share only the predicate, not the behavior.

---
filed: 2026-10-20
where:
  - src/confarg/cli/_build.py::_arity_rank
  - src/confarg/cli/_build.py::_shaped
  - src/confarg/cli/_build.py::_binds_a_run
effort: S
risk: low
impact: none
severity: trivial
---

# REF-112 — `_arity_rank` repeats the shape decision `_shaped` owns

BUG-198 made `cli/_build._shaped` the one decision of a flag's token shape — a run for a multi-token type (`_takes_multi_tokens`), one token per position for a fixed-arity one (`_fixed_seq_types`), one token otherwise ([a-flag-that-stands-bare.md](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)).
`_arity_rank`, added in the same range to pick the widest of a flag's typed occurrences in `_collect_loop_typed_specs`, re-tests the same two predicates in the same order to rank 2, 1, 0; `_binds_a_run` tests them a third time for "does a greedy host bind a run here", and `bound_runs` reads the answer back off registered specs.

Fix direction: one `_token_shape(tp)` enum (`RUN`, `FIXED`, `ONE`) which `_shaped` turns into spec attributes, `_arity_rank` orders, and `_binds_a_run` reads as `is not ONE`.

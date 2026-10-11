---
filed: 2026-10-07
where:
  - docs-agents/testing.md  # the "Where a test goes" table
effort: S
risk: low
impact: none
severity: trivial
---
# FEAT-36 — The test-routing table has no row for `_sources.py` or `_defaults.py`

The "Where a test goes" table in the testing protocol maps each source module to its test file,
but has no row for `src/confarg/_sources.py` — which has its own `tests/test_sources.py` (scheme
dispatch, reading, format, joining, identity) — nor for `src/confarg/_defaults.py`, whose
coverage sits in `tests/test_load_api.py` (behind the `_api.py` row) and
`tests/test_coverage_gaps.py`. An agent changing either module gets no pointer to where its
tests live. PR-208 added `_sources.py` and its tests and updated the versioned notes, but could
not see the unversioned protocol — the same blind spot as BUG-149, BUG-150 and BUG-203. Fix
direction: add the two rows, `_defaults.py` pointing at `test_load_api.py`.

Why the layout is what it is, is argued in
[testing.md#layout](../../architecture/testing.md#layout).

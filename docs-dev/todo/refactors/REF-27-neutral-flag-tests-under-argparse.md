# REF-27 — Tests of the neutral flag model still live under `tests/cli/argparse/`

**Where:** `tests/cli/argparse/test_gaps.py`, `test_final.py` · **Filed:** 2026-09-15
**Effort:** M · **Risk:** low · **Impact:** none

REF-1 moved `_spec.py` and `_build.py` to `cli/`, but their tests stayed where they were, so
`tests/` no longer mirrors `src/confarg/`. `test_gaps.py` mixes specs-and-build tests with
genuinely argparse-specific `_register` / `_completion` ones; `test_final.py` is a topic file
(Final support across coercion, build and completion) that resists a clean split. Extract the
neutral halves into `tests/cli/test_build.py` / `test_spec.py`, or decide the topic layout wins
over the mirror rule and say so in [12-testing.md](../../architecture/12-testing.md).

---
filed: 2026-09-15
where:
  - tests/cli/argparse/test_gaps.py
  - tests/cli/argparse/test_final.py
effort: M
risk: low
impact: none
severity: trivial
---

# REF-27 — Tests of the neutral flag model still live under `tests/cli/argparse/`

REF-1 moved `_spec.py` and `_build.py` to `cli/`, but their tests stayed where they were, so `tests/` no longer mirrors `src/confarg/`.
`test_gaps.py` mixes specs-and-build tests with genuinely argparse-specific `_register` / `_completion` ones; `test_final.py` is a topic file (Final support across coercion, build and completion) that resists a clean split.
Extract the neutral halves into `tests/cli/test_build.py` / `test_spec.py`, or decide the topic layout wins over the mirror rule and say so in [testing.md](../../architecture/testing.md).

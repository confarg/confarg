# REF-78 — Subsumed `or`-disjuncts in tests read like the or-asserts-away family

**Where:** `tests/test_errors.py` (`test_scalar_target_missing_value_message`) ·
`tests/test_hypothesis.py` (`test_float_round_trip`, `test_float_round_trip_env`)
· **Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

Three assertions carry a disjunct strictly implied by the other, so each is exactly as strong
as its surviving clause — but the `or` reads like the or-asserts-away family (REF-38,
closed; and [REF-39](REF-39-dict-field-env-test-or-asserts-away-claim.md)), where an `or`
made the asserted claim non-load-bearing, and suggests two distinct cases where there is one:

- `assert "CLI" in msg or "cli" in msg.lower()` — any `"CLI"` in `msg` lowercases to
  `"cli"`, so the first clause is implied by the second; likewise
  `"environment" in msg or "env" in msg.lower()` (`"environment"` contains `"env"`).
- `assert abs(result.rate - value) < 1e-6 or result.rate == value` — exact equality
  implies a zero difference, so the second clause never adds a case.

Fix: drop the dead disjunct, leaving `"cli" in msg.lower()`, `"env" in msg.lower()` and
`abs(result.rate - value) < 1e-6`. The property tests are the pattern this touches
([testing.md#property-tests](../../architecture/testing.md#property-tests)).

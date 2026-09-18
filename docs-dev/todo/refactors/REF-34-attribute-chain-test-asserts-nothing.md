# REF-34 — An _attribute_chain test asserts what it does not verify

**Where:** `tests/test_coverage_gaps.py` (`test_attribute_chain_subscript_at_top`)
· **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

The test claims `_attribute_chain` handles a top-level integer subscript
gracefully, but its assertion is `assert result is None or isinstance(result,
list)` — a list is the success shape of `_attribute_chain`, so the test passes
whether the function returns a list or `None`. The call actually returns
`['a', '0']` for `a[0]` (verified). Same family as REF-30: tighten to
`assert result == ["a", "0"]` to pin the chain it produces. The integer-subscript
behavior the test exercises is part of the expression
[safety model](../../architecture/07-expressions.md#safety-model).

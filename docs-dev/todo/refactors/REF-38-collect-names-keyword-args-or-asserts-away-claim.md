# REF-38 — `test_collect_names_keyword_args` or-asserts away its own claim

**Where:** `tests/test_coverage_gaps.py` (`TestExpressionBranches.test_collect_names_keyword_args`)
· **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

The test's docstring and inline comment claim the keyword argument name `y` is
collected as a reference, but the body asserts `assert "x" in refs or "y" in refs`.
The `or` makes `y` non-load-bearing: `x` is always collected for
`${sorted(x, key=y)}`, so the test passes even if keyword-arg collection regressed.
Verified `_extract_references("${sorted(x, key=y)}")` returns `{'x', 'y'}` — both
present, so it passes for the right reason today, but would not catch the regression
it exists to pin. Same family as REF-34/REF-36: rewrite to `assert "y" in refs`
(drop the `or` and the unrelated `x`). Reference collection is part of the expression
[safety model](../../architecture/07-expressions.md#safety-model).

# REF-37 — `test_extract_refs_syntax_error_skipped` asserts the return type, not emptiness

**Where:** `tests/test_coverage_gaps.py` (`TestExpressionBranches.test_extract_refs_syntax_error_skipped`)
· **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

The test's docstring claims invalid expression content "yields an empty reference
set," but the body asserts only `assert isinstance(refs, set)` — true of any set,
empty or not. A regression that returned a non-empty set would still pass. Verified
`_extract_references("${invalid syntax!!!}")` does return `set()`. Same family as
REF-34/REF-36: rewrite the assertion to `assert refs == set()` (or `assert not refs`).
The syntax-error skip is part of the expression
[safety model](../../architecture/07-expressions.md#safety-model).

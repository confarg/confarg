# REF-36 — A second _attribute_chain test asserts what it does not verify

**Where:** `tests/test_coverage_gaps.py` (`test_attribute_chain_noninteger_subscript_returns_none`)
· **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

The test's name and docstring claim `_attribute_chain` returns `None` for
string subscripts (non-integer indices), but the body calls `_extract_references`
and asserts `assert isinstance(refs, set)` — which only checks the return *type*
of `_extract_references`, not anything about `_attribute_chain`. The assertion
passes regardless of whether `_attribute_chain` returns `None` or a list.
Verified `_attribute_chain(ast.parse("servers['primary'].host", mode="eval").body)`
does return `None`. Same family as REF-34: rewrite the body to call
`_attribute_chain` directly and assert `result is None`, dropping the unrelated
`_extract_references`/`isinstance` check. The integer-vs-string subscript split
is part of the expression
[safety model](../../architecture/07-expressions.md#safety-model).

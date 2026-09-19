# REF-30 — A _resolve_struct test asserts what it does not verify

**Where:** `tests/cli/argparse/test_gaps.py` (`test_resolve_struct_struct_fields_raises`)
· **Filed:** 2026-09-17
**Effort:** S · **Risk:** low · **Impact:** none

The test claims `_resolve_struct` returns `None` when `_struct_fields` raises, but its
assertion is `assert result is None or isinstance(result, tuple)` — a tuple is the
*success* shape of `_resolve_struct`, so the test would still pass if a regression made the
function return one instead of `None`. Verified the call currently returns `None`. Same
family as REF-14: tighten to `assert result is None`.

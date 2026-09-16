# REF-14 — A dynamic-flag test passes for the wrong reason

**Where:** `tests/cli/argparse/test_gaps.py` (`test_build_dynamic_flags_exception_returns_empty`)
· **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** none

The test claims to exercise the error handler in `build_dynamic_flags` by passing `None` as
the target, but `None` raises nothing: the scan simply finds no flags and returns `[]`.
Verified while closing BUG-5 — with the handler now warning, that call emits no warning, so
the handler is never reached. The monkeypatch test next to it
(`test_build_dynamic_flags_warns_on_internal_error`) already covers the real path, so this
one is either deleted or rewritten around an input that genuinely fails.

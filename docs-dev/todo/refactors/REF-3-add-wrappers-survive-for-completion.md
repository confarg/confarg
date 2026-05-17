# REF-3 — `_add_*` wrappers survive only for completion

**Where:** `src/confarg/cli/argparse/_register.py` · **Filed:** 2026-09-12
**Effort:** M · **Risk:** medium · **Impact:** none

The thin `_add_*` helpers exist because `_completion.py` needs the `argparse` action objects.
Refactoring completion onto `FlagSpec` would delete them.

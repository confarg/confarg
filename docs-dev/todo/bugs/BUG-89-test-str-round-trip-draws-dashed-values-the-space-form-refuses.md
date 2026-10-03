# BUG-89 — `test_str_round_trip` draws dashed values the space form refuses by design

**Where:** `tests/test_hypothesis.py` (`TestRoundTripCoercion::test_str_round_trip`) ·
**Filed:** 2026-09-30
**Effort:** S · **Risk:** low · **Impact:** none

`test_str_round_trip` feeds `leaf_strs` values to `--name` in the space form, but the space
form refuses a value that starts with `--` on every front-end — the `=` form is the documented
escape
([equals-escapes-a-dashed-value](../../architecture/design-decisions/equals-escapes-a-dashed-value.md#the--form-is-the-escape-for-a-dashed-value)).
So the suite goes red whenever Hypothesis draws a dashed value: full-suite runs found `--A`
and `--=` (2026-09-30), single-test runs pass again because the example database only replays
what it kept. `test_set_round_trip` in the same file already filters with
`_looks_like_flag`; this test is the one that forgot.

Fix direction: filter the strategy the same way —
`leaf_strs.filter(lambda s: not _looks_like_flag(s))` — or switch the test to the `=` form
(`argv=[f"--name={value}"]`), which is the escape the documented behavior points to.

```python
# the failing full-suite run (uv run pytest -p no:markdown-console):
# FAILED tests/test_hypothesis.py::TestRoundTripCoercion::test_str_round_trip
#   - ExceptionGroup: Hypothesis found 2 distinct failures
#   Failing test case: test_str_round_trip(value='--A')
#   confarg.exceptions.ConfargError: Missing value for '--name'. Usage: --name <value>
#   Failing test case: test_str_round_trip(value='--=')
#   confarg.exceptions.UnknownArgumentError: Unexpected positional argument: ''.
#
# reproduced directly (intended parser behavior, so the test is what must give):
import confarg
from tests.conftest import WithDefaults

confarg.load(WithDefaults, argv=["--name", "--A"], env={})
# expected by the test: WithDefaults(name='--A')
# actual:   ConfargError: Missing value for '--name'. Usage: --name <value>
```

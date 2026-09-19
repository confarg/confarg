# REF-39 — `test_dict_field_from_env` or-asserts away its own claim

**Where:** `tests/test_coverage_gaps.py` (`TestEnvParsingEdgeCases.test_dict_field_from_env`)
· **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

The test's docstring claims a dict-typed field is "populated from env vars
using double-underscore key separation," but the body asserts
`result.mapping.get("key") == 42 or "key" in result.mapping`. The `or` makes
the value non-load-bearing: if the value came through wrong (wrong type, wrong
number), the second clause (`"key" in result.mapping`) still passes as long as
the key is present. Verified
`confarg.load(WithDict, env={"MYAPP_MAPPING__KEY": "42"}, env_prefix="MYAPP_")`
returns `mapping == {"key": 42}` with `42` an int — so the test passes for the
right reason today, but would not catch a value-coercion regression it exists
to pin. Same family as REF-38: rewrite to `assert result.mapping.get("key") == 42`
(drop the `or` and the unrelated key-presence check), or strengthen to
`assert result.mapping == {"key": 42}`. The double-underscore separator is the
design decision at
[10-design-decisions.md#double-underscore-separator](../../architecture/10-design-decisions.md#double-underscore-separator).

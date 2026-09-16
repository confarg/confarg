# REF-22 — `_store_env_value` buries a JSON-autodetect predicate in nested `any(...)` calls

**Where:** `src/confarg/_parse_env.py` (`_store_env_value`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** none

`_store_env_value` (lines 289-326) builds two large boolean expressions `accepts_obj` / `accepts_arr`
with triple-nested `any(... for v in _union_args_no_none(ft))` checks to decide whether a `[`/`{`-led
env value should be parsed as JSON. Extract `_accepts_json_for(ft, value) -> bool` (returns True
when `ft` is a struct/namedtuple/dict/callable/union-with-such and the value's opening bracket
matches); the body then reads as a clean three-step: try JSON autodetect, else `_try_coerce`.
Reduces nesting and ~10 lines.

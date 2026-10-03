# REF-77 — The four "expected N elements" refusals have drifted on the type's name

**Where:** `src/confarg/typedload/_construct.py` · **Filed:** 2026-10-03
**Effort:** S · **Risk:** medium · **Impact:** none

The arity refusals — "Cannot construct X at '`<path>`': expected N elements, got M" — are a
construction-error family still spelled at each of its four sites (L143, L647, L652, L662),
and they have already drifted the way
[messages-live-on-exceptions.md](../../architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)
warns about: the namedtuple site names the type by `__name__`, the three fixed-tuple sites by
full repr, and no test pins either spelling — `tests/cli/test_backend_contract.py`,
`tests/test_env.py` and `tests/test_namedtuple.py` match only the "expected N elements" tail.
Observed on the parent of the REF-69 revision, with `construct(Point, [1, 2, 3], path="p")`
against `construct(tuple[int, str], [1, 2, 3], path="p")`:

```
Cannot construct Point at 'p': expected 2 elements, got 3
Cannot construct tuple[int, str] at 'p': expected 2 elements, got 3
```

One factory parametrized by the count pair serves all four, in the wake of
`TypeCoercionError.wrong_shape` (REF-69); it must settle which name spelling wins and pin it.

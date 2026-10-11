---
filed: 2026-10-07
where:
  - tests/test_callables.py::TestBindDictForm  # test_fn_is_an_ordinary_argument
effort: S
risk: low
impact: none
severity: trivial  # test hygiene: the suite passes, only the type checker fails
introduced_by: [FEAT-30]  # added the test
---
# BUG-189 — A `bind:` test calls a one-argument callable by keyword, which `ty check` refuses

`test_fn_is_an_ordinary_argument` loads `WithCallable`, whose field is `Callable[[int], int]`,
and calls it as `result.fn(x=3)`. A `Callable[[int], int]` takes its argument by position only,
so `uvx --with click --with argcomplete ty check` reports two errors, and the check that every
change must pass is not clean. The test itself passes, because at run time the field holds a
partial of `_with_fn_param(fn, x)`. Fix direction: load a target whose field admits a keyword
call, `Callable[..., int]` or the bare `WithBareCallable`.

Origin: introduced by FEAT-30, which added the test when `fn` stopped being a directive word and
became an ordinary argument name. The type checker was not run on the test, or its result was
not read. Not a regression: the test is new.

```console
$ uvx --with click --with argcomplete ty check
error[missing-argument]: No argument provided for required parameter 1
   --> tests\test_callables.py:561:16
error[unknown-argument]: Argument `x` does not match any known parameter
   --> tests\test_callables.py:561:26
# expected: no diagnostic in tests/test_callables.py
# actual:   the two errors above (line 496 on the FEAT-30 revision itself)
```

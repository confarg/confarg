# BUG-146 — A power or a repeated string has no size bound

**Where:** `src/confarg/dictexpr/_expressions.py` (`_BINOP_MAP`, `_eval_binop`) ·
**Filed:** 2026-10-03
**Effort:** L · **Risk:** high · **Impact:** config

The interpreter exists so that configuration nobody trusts can be evaluated without `eval`
([design decision](../../architecture/design-decisions/expressions-resolved-after-merging.md)),
and expressions arrive from env and argv too
([safety model](../../architecture/expressions/safety-model.md)). But `**` and `*` go straight
to `operator.pow` and `operator.mul`, so a value a few characters long can stall `resolve()`.
Each extra digit in an exponent costs roughly 35 times more: `${10 ** 10 ** 7}` takes 17 s,
`${10 ** 10 ** 8}` about ten minutes, and `${9 ** 9 ** 9}` never finishes. A repeated string
allocates whatever it is asked to (`'ab' * 10 ** 8` is 200 MB). The fix needs a decision on the
bounds, recorded under `expressions/`. Two precedents bound the operands before computing:
simpleeval caps an exponent at `MAX_POWER` (4 000 000) and a string at `MAX_STRING_LENGTH`
(100 000), and CPython limits int↔str conversion to 4 300 digits (CVE-2020-10735). Any bound
refuses a value that resolves today, hence `config`, though a real configuration is unlikely to
come near one.

```python
import time

import confarg

for value in ("${10 ** 10 ** 6}", "${10 ** 10 ** 7}", "${len('ab' * 10 ** 8)}"):
    start = time.perf_counter()
    result = confarg.resolve({"v": value})["v"]
    print(f"{value}: {type(result).__name__} after {time.perf_counter() - start:.1f}s")
# expected: each refused at once, as an UnsafeExpressionError naming the expression
# actual:
# ${10 ** 10 ** 6}: int after 0.5s
# ${10 ** 10 ** 7}: int after 17.0s
# ${len('ab' * 10 ** 8)}: int after 0.2s
```

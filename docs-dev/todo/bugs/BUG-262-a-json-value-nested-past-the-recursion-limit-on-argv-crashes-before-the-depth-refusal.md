---
filed: 2026-10-20
where:
  - src/confarg/_parse_cli.py::_argv_named_nodes
effort: S
risk: medium
impact: behavior
severity: minor  # invalid input answered with a raw exception
introduced_by: [BUG-233, BUG-236, BUG-110, BUG-114]  # the lexical naming scan of argv
---

# BUG-262 — A JSON value nested past the recursion limit on argv crashes before the depth refusal

A `{…}` value or a `.json` cast on argv nested a little over a thousand levels raises a bare `RecursionError` instead of the `ConfargError` every other deep value gets.
`_argv_named_nodes` runs when `_ParseCtx` is built, before vanilla's loop meets the flag: it decodes the value with `json.loads` rather than `_cast.decode_json` — the one decoder of a JSON value on argv or in the environment, which turns the decoder's own `RecursionError` into `ConfargError.too_deep` and counts the value against `_depth.MAX_DEPTH` — and then walks it with the recursive `nested()`.
At 70 levels the scan survives and the loop refuses the value as [a configuration nests at most 64 levels](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#where-it-is-counted) says; past Python's recursion limit `nested()` (and, deeper, `json.loads` itself) gives up first.
Every front-end meets it, the adapters' CLI channel being the same loop.

Fix direction: decode through `decode_json` and swallow its `ConfargError` as the scan already swallows `json.JSONDecodeError` — the scan is lexical and leaves the refusal to the loop — so the walk only ever meets a value within the bound. [a-decoded-value-is-data.md](../../architecture/design-decisions/a-decoded-value-is-data.md#a-decoded-value-is-data)

Origin: regression from the fix for BUG-233, BUG-236, BUG-110 and BUG-114, which added the scan to tell which nodes argv names, so that a lower layer's naming types none of them.
It decoded with `json.loads` because the scan must not refuse what the loop has not reached yet.
The later fix for BUG-248 routed every decode site through `decode_json` and the depth count, and missed this one, so BUG-248's "wherever it enters" does not hold on argv.

```python
from dataclasses import dataclass, field
from typing import Any

import confarg


@dataclass
class Config:
    d: dict[str, Any] = field(default_factory=dict)


for depth in (70, 1200):
    deep = '{"a":' * depth + "1" + "}" * depth
    try:
        confarg.load(Config, argv=["--d", deep])
    except Exception as e:
        print(depth, type(e).__name__, str(e)[:80])

# expected: 1200 ConfargError Cannot set '--d': it nests deeper than 64 levels, ...
# actual:
# 70 ConfargError Cannot set '--d': it nests deeper than 64 levels, at 'd.a.a ... a.a' (65 levels)
# 1200 RecursionError maximum recursion depth exceeded
```

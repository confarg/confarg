---
filed: 2026-11-11
where:
  - src/confarg/_parse_env.py::_store_env_value  # stores a variable's text as the whole value
  - src/confarg/_parse_cli.py::_varlen_value  # argv's lone token is one item
  - src/confarg/_parse_cli.py::_union_seq_value  # argv's lone token falls back to a one-item list
effort: M  # which types read a lone value as one item, and the expression a lone value may be (BUG-257)
needs_design: true  # whether the environment reads a lone value as one item, or argv stops doing so
risk: medium  # every list, set, variadic tuple and scalar-or-sequence union a variable sets
impact: behavior  # a refused variable starts building a one-item list
severity: minor  # refused loudly; `APP_TAGS='["a"]'` builds the list
introduced_by: [PR-5]  # the CLI read every token of a list flag as an item, the environment the variable as the value
---

# BUG-325 — A lone variable value is no one-item list

`--tags a` builds `['a']` at a `list[str]` field, and `--x hello` builds `['hello']` at a `bool | list[str]` one (the `_UnionSeqToken` fallback), but `APP_TAGS=a` and `APP_X=hello` are refused: the environment stores the variable's text as the whole value, which construction then refuses as no list.
A variable has no multi-item spelling but JSON, so the environment spells a one-item list `APP_TAGS='["a"]'` only, where argv spells it either way ([token consumption](../../architecture/cli-parsing/token-consumption.md#unions-with-sequence-variants), whose note says only that env scalars "express lists explicitly").
Fix direction: decide whether a lone variable value is one item, as a lone token is, or the difference is a recorded channel boundary ([limitations](../../architecture/limitations.md)); [BUG-257](BUG-257-a-lone-expression-token-on-a-list-flag-is-one-item.md) is the same split read the other way, a lone `${...}` token, which the environment reads as the whole list and argv as one item.

Origin: latent since the initial version (PR-5), whose CLI made every token of a list flag an item and whose environment parser stored a variable's text as the whole value, as BUG-257's origin says.

```python
from dataclasses import dataclass, field

import confarg
from confarg.exceptions import ConfargError


@dataclass
class C:
    tags: list[str] = field(default_factory=list)
    x: bool | list[str] = False


for argv, env in ((["--tags", "a"], {}), ([], {"APP_TAGS": "a"}), (["--x", "hello"], {}), ([], {"APP_X": "hello"})):
    try:
        print(confarg.load(C, argv=argv, env=env, env_prefix="APP_"))
    except ConfargError as e:
        print(f"{type(e).__name__}: {e}".splitlines()[0])
# expected: C(tags=['a'], x=False)
#           C(tags=['a'], x=False)
#           C(tags=[], x=['hello'])
#           C(tags=[], x=['hello'])
# actual:   C(tags=['a'], x=False)
#           TypeCoercionError: Cannot construct list at 'tags': expected list, tuple, or dict with integer keys, got str 'a'
#           C(tags=[], x=['hello'])
#           TypeCoercionError: Cannot coerce str 'hello' to bool | list[str] at 'x':
```

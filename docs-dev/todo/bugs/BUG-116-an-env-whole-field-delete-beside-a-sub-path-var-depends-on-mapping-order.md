# BUG-116 — An env whole-field delete beside a sub-path variable depends on the mapping's order

**Where:** `src/confarg/_parse_env.py` (`_parse_env`'s `for orig_key, value in env.items()`
loop, `_handle_env_delete`) · **Filed:** 2026-10-01
**Effort:** S · **Risk:** low · **Impact:** behavior

`FOO__USERS-` beside `FOO__USERS__0=x` (or `FOO__USERS__0-`) is resolved by whichever the
mapping yields last: the whole-field delete replaces the sub-path op, and the sub-path op
replaces the delete's sentinel. That is the CLI's "last typed wins" rule, but the
environment has no typing order — REF-44 settled the same problem for a scalar root and
`<PREFIX>JSON` by making the result order-independent
([environment-parsing.md](../../architecture/environment-parsing.md#environment-parsing)).
Found while fixing BUG-77, which made the index-delete half stop crashing in one of the two
orders.

Fix direction, for the maintainer to pick: the delete always wins (the variable asking to
clear the field is honored whatever sits beside it), or the sub-path op always wins (it
refines the field, as a per-field variable refines `<PREFIX>JSON`), or the pair is refused
as a conflict. Whichever is chosen, `tests/test_env.py::TestEnvDelete::test_delete_list_index_after_whole_field_delete`
pins one order today and should pin both.

[pipeline/deep-merge.md#scalar-intermediates](../../architecture/pipeline/deep-merge.md#scalar-intermediates)

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class Config:
    users: list[str] = field(default_factory=list)


env = {"APP__USERS-": "", "APP__USERS__0": "x"}
print(confarg.merge(Config, argv=[], env=env, env_prefix="APP"))
print(confarg.merge(Config, argv=[], env=dict(reversed(env.items())), env_prefix="APP"))

# expected: the same result for both orders
# actual:   {'users': {'0': 'x'}}
#           {}
```

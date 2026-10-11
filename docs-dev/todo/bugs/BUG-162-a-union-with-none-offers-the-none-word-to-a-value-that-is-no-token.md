---
filed: 2026-10-05
where:
  - src/confarg/typedload/_construct.py::_construct_union_leaf
effort: S
risk: medium
impact: behavior
---
# BUG-162 — A union with `None` offers the none word to a value that is no token

When no variant of a multi-variant union with `None` accepts a value, `_construct_union_leaf`
appends the none-word remedy whatever the value is. A none word is only read off a token, so
for a file's string the remedy is wrong: a file's `"none"` stays a string, so the message tells
the user to write the very value it just refused. The single-variant union stopped doing this
in BUG-159; this site should apply the same rule, through the same `reads_none_word` test (a
`_StrToken` and `None` among the variants), rather than a second spelling of it. See
[an optional field fails as its variant](../../architecture/types/construction.md#an-optional-field-fails-as-its-variant)
and the [token model](../../architecture/types/token-model.md#token-model).

```python
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    v: int | float | None = None


try:
    confarg.build(Config, {"v": "none"})  # a file's string: YAML `v: none`, JSON `"v": "none"`
except confarg.exceptions.TypeCoercionError as e:
    print(e)

# expected: Cannot coerce str 'none' to int | float | None at 'v'
# actual:   Cannot coerce str 'none' to int | float | None at 'v'. To set this field to None, pass 'none' or 'null'.
```

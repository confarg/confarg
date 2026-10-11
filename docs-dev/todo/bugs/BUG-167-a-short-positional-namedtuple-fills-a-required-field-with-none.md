---
filed: 2026-10-05
where:
  - src/confarg/typedload/_construct.py::_construct_namedtuple
effort: S
risk: high
impact: config
---
# BUG-167 — A short positional namedtuple fills a required field with `None`

A positional list shorter than a namedtuple fills each missing position with its default, and
with `None` when the field has none (`defs.get(field_names[i])` in `_construct_namedtuple`).
So `[1]` for `P(x: int, y: int)` fails with `Cannot coerce NoneType None to int at 'p.y'`,
which names a `None` nobody passed. For `R(x: int, y: int | None)`, `[1]` silently builds
`R(1, None)`. The same field left out of the dict spellings (`{'x': 1}`, `{'0': 1}`) is the
`MissingFieldError` naming `--p.y`, the
[canonical error for a field no channel supplied](../../architecture/invariants.md#delegate-to-the-canonical-function)
(`_missing_field_error`). The positional form should raise that error too. Every channel
reaches it: a file's `[1]`, `APP_P='[1]'`, `--p '[1]'`, and `--p 1` on a `P | None` field,
whose union dispatch consumes greedily. A short list over defaulted fields keeps building
(`Q(x: int, y: int = 5)` from `[1]` is `Q(1, 5)`), so the fix is only for a position with no
default.

```python
from dataclasses import dataclass
from typing import NamedTuple

import confarg


class P(NamedTuple):
    x: int
    y: int


class R(NamedTuple):
    x: int
    y: int | None


@dataclass
class C:
    p: P


@dataclass
class E:
    r: R


for target, data in [(C, {"p": [1]}), (C, {"p": {"x": 1}}), (E, {"r": [1]})]:
    try:
        print(data, "->", confarg.build(target, data))
    except confarg.exceptions.ConfargError as e:
        print(data, "->", type(e).__name__, e)

# expected: MissingFieldError for 'p.y' twice, and MissingFieldError for 'r.y'
# actual:
#   {'p': [1]} -> TypeCoercionError Cannot coerce NoneType None to int at 'p.y'
#   {'p': {'x': 1}} -> MissingFieldError Missing required field 'p.y' of type <class 'int'>. Set it via CLI (--p.y), environment variable, or config file.
#   {'r': [1]} -> E(r=R(x=1, y=None))
```

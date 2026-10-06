---
filed: 2026-10-05
where:
  - src/confarg/typedload/_construct.py::_construct_struct
  - src/confarg/typedload/_construct.py::_call_with_var_positional
effort: S
risk: high
impact: behavior
severity: major
introduced_by: [PR-5]  # _construct_struct calls a plain class by keyword unless it takes *args
---
# BUG-152 — A positional-only `__init__` parameter fails `build()` with a raw `TypeError`

`_construct_struct` calls a plain class as `tp(**kwargs)` unless its `__init__` takes `*args`,
so a positional-only parameter (`def __init__(self, a, /)`) is passed by keyword and CPython
refuses the call. The error escapes `build()` as a stdlib `TypeError`, not a `ConfargError`,
on every channel and front-end. With `*args` the same class builds, because
`_call_with_var_positional` passes `_init_params(tp).positional` by position. Fix direction: one
call path for every plain class, filling the positional names by position as that function
does ([types/introspection.md](../../architecture/types/introspection.md#introspection-is-cached-per-class)).

Origin: latent since the initial version (PR-5), which already passed the positional names by
position for a class taking `*args` and called every other plain class by keyword. It reproduces
unchanged at PR-28, the oldest revision the reproduction runs on. BUG-156 is the same miss in the
callable specs, from the same revision.

```python
from dataclasses import dataclass

import confarg


class PosOnly:
    def __init__(self, a: int, /) -> None:
        self.a = a


@dataclass
class Config:
    item: PosOnly


print(confarg.load(Config, argv=["--item.a", "1"]).item.a)
# expected: 1
# actual:   TypeError: PosOnly.__init__() got some positional-only arguments passed as keyword arguments: 'a'
```

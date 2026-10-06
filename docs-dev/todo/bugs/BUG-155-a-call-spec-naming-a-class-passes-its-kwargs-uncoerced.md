---
filed: 2026-10-05
where:
  - src/confarg/_callable.py::_resolve_call_kwargs
effort: S
risk: high
impact: behavior
severity: critical  # the constructor silently receives the string
introduced_by: [PR-5]  # get_type_hints(func) in _resolve_call_kwargs; PR-93 kept it for call:
---
# BUG-155 — A `call:` spec naming a class passes its kwargs uncoerced

`_resolve_call_kwargs` reads the type hints of the object it calls. For a class, those are the
class's own attribute annotations, not its `__init__` parameters, so a `call:` that names a class
builds no kwarg at all: a CLI or environment token reaches the constructor as a raw `_StrToken`.
That breaks [tokens mean untyped text](../../architecture/invariants.md#tokens-mean-untyped-text)
and the [one coercion route](../../architecture/callables.md#one-coercion-route) that `class:` and
`bind:` already follow. Fix direction: take the hints from `_bind_hints_source(func)`, as
`_resolve_bind_kwargs` does, which answers `__init__` for a class.

Origin: latent since the initial version (PR-5), whose `_resolve_call_kwargs` read
`get_type_hints(func)`, which answers a class's attribute annotations. PR-93 added
`_bind_hints_source` so that `bind:` and `class:` read `__init__`, and left `call:` on the old
source (`_coerce_kwargs(func, func, …)`), so the case was missed a second time there.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


class Adder:
    def __init__(self, k: int) -> None:
        self.k = k

    def __call__(self, v: int) -> int:
        return v + self.k


@dataclass
class Config:
    f: Callable[[int], int]


print("class:", repr(confarg.load(Config, argv=["--f.class", "__main__.Adder", "--f.k", "2"]).f.k))
print("call: ", repr(confarg.load(Config, argv=["--f.call", "__main__.Adder", "--f.k", "2"]).f.k))
# expected: class: 2
#           call:  2
# actual:   class: 2
#           call:  '2'
```

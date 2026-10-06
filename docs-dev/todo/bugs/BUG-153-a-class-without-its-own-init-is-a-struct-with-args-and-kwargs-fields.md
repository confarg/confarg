---
filed: 2026-10-05
where:
  - src/confarg/_types.py::_is_plain_class
  - src/confarg/_types.py::_init_params
effort: S
risk: high
impact: config  # if such a class becomes a leaf, a config that omits it stops building
severity: minor  # only a flag that should not exist fails; the class still builds
needs_design: true
introduced_by: [PR-5]  # _is_plain_class and _init_params read an inherited object.__init__ as parameters
---
# BUG-153 — A class without its own `__init__` is a struct with `args` and `kwargs` fields

A struct is "a plain class whose `__init__` takes parameters"
([types/introspection.md](../../architecture/types/introspection.md#type-introspection)). A
class that defines no `__init__` inherits `object.__init__`, whose signature reads
`(self, /, *args, **kwargs)`, so it counts as a struct with an `args` list and a `kwargs` dict:
`--marker.kwargs.x` merges, then `build()` fails with a raw `TypeError`, since
`object.__init__` takes no arguments. A class declaring `def __init__(self)` is a leaf instead,
so the two spellings of "takes nothing" disagree. The design pass decides what such a class
is — a leaf, or a struct with no fields — which also decides whether a config omitting the
field still builds: today the all-defaults shortcut builds `Marker()` from nothing.

Origin: latent since the initial version (PR-5): a plain class is a struct when its `__init__`
signature has parameters, and that read never told an inherited `object.__init__` from one the class
declares. Before PR-39 (namedtuple support) `build()` refused the `kwargs` field with a
`TypeCoercionError`; since PR-39 the call reaches `Marker()` and escapes as a raw `TypeError`
(bisected).

```python
from dataclasses import dataclass

import confarg


class Marker:
    """No __init__ of its own."""


@dataclass
class Holder:
    marker: Marker


print(confarg.merge(Holder, argv=["--marker.kwargs.x", "1"]))
confarg.load(Holder, argv=["--marker.kwargs.x", "1"])
# expected: --marker.kwargs.x refused as an unknown flag, as for a class declaring __init__(self)
# actual:   {'marker': {'kwargs': {'x': '1'}}}
#           TypeError: Marker() takes no arguments
```

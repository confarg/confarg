---
filed: 2026-10-07
where:
  - src/confarg/_callable.py::_resolve_class_spec  # the stamp
  - src/confarg/_callable.py::_resolve_classfn_spec  # the owner's stamp
  - src/confarg/_callable.py::_serialize_callable
effort: M
risk: low
impact: behavior
severity: critical  # a change made after build() is dropped from the dump with no error
needs_design: true  # how a callable instance's state is read, and what happens to one that does not store it
introduced_by: [PR-5]  # the initial version dumps a class: instance from its stamp only
---
# BUG-192 — A `class:` instance dumps the arguments it was built with, not the values it holds

`dump()` writes the state of the built object
([the object dump writes state](../../architecture/design-decisions/the-object-dump-writes-state.md)).
A `class:` instance on a Callable field, and a `classfn:` method's owner, dump from the spec
stamped on them at `build()` instead. A change made to them afterwards is lost from the dump, as
the limitation records ([limitations](../../architecture/limitations.md#callables-and-serialization)).
An instance that refuses the stamp, such as a frozen dataclass, has nothing to dump from at all:
`dump()` raises, and its message blames a missing `__qualname__` rather than the refused stamp.

A struct field already reads state: its fields come from the same-named attributes, and the class
tag names its type. Reading a callable instance the same way would dump its current values, and
would work for a frozen one. A class that does not store its constructor arguments as attributes
would then have no dump, where it dumps its stamp today. Whether the stamp stays as a fallback
for such a class is the design question.

Origin: the initial version stamped every `class:` instance with its spec, so that `dump()` could
write a Callable field back at all. A callable instance has no field list a dataclass would give
it. The bug is latent: the stamp never tracked later changes, and the rule it breaks was only
written down when FEAT-33 was declined.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


class Scaler:
    def __init__(self, factor: int) -> None:
        self.factor = factor

    def __call__(self, x: int) -> int:
        return x * self.factor


@dataclass(frozen=True)
class FrozenScaler:
    factor: int

    def __call__(self, x: int) -> int:
        return x * self.factor


@dataclass
class Config:
    f: Callable[[int], int]


cfg = confarg.from_dict(Config, {"f": {"class": "__main__.Scaler", "factor": 3}})
cfg.f.factor = 5
print(confarg.dump(cfg))
# expected: {'f': {'class': '__main__.Scaler', 'factor': 5}}
# actual:   {'f': {'class': '__main__.Scaler', 'factor': 3}}

cfg = confarg.from_dict(Config, {"f": {"class": "__main__.FrozenScaler", "factor": 3}})
print(confarg.dump(cfg))
# expected: {'f': {'class': '__main__.FrozenScaler', 'factor': 3}}
# actual:   confarg.exceptions.ConfargError: Cannot serialize callable FrozenScaler(factor=3):
#           no __module__/__qualname__ available. For class instances, ensure the instance was
#           constructed via confarg (which stores the spec for round-trip serialization).
```

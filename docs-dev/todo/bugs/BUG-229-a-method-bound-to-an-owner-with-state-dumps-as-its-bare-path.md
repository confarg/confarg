---
filed: 2026-10-11
where:
  - src/confarg/_callable.py::_serialize_callable
  - src/confarg/_callable.py::_reads_back_from
effort: S
risk: low
impact: behavior
severity: critical  # the owner's state is dropped from the dump with no error
needs_design: true  # refuse such a method at dump(), or read the owner's state as BUG-192 plans to
introduced_by: [PR-5]  # the initial version writes any bound method as module + qualname
---
# BUG-229 — A method bound to an owner that holds state dumps as its bare path, losing the state

`dump()` writes a bound method as the dotted path to its function, which reads back by
[auto-binding](../../architecture/callables.md#auto-binding): bound to a new owner built with no
arguments. That is the method again only when the owner was built that way. A method bound to an
owner the user built in Python, or one whose attributes changed after `build()`, dumps the same
path, and its state is lost silently. A `call:` whose factory returns such a method, as the second case below does, is dumped the same way: since BUG-191 a `call:` result dumps as what it is, and a bound method never took the call's stamp anyway, since it refuses attributes. `_reads_back_from` checks the owner's class, not its state
([round-trip](../../architecture/callables.md#a-path-is-written-only-when-it-reads-back)).

The `classfn:` owner is the stamped case of the same thing, and BUG-192 asks how a callable
instance's state is read at all. One answer probably settles both: dump the owner's state as a
`classfn:` spec, or refuse a method whose owner confarg did not build with no arguments, which
needs a mark on the owners auto-binding builds.

Origin: the initial version wrote any callable with a module and a qualified name as their
dotted join, and auto-bound a path naming an instance method, so a bound method dumped as a path
whatever its owner held. Latent since then. BUG-193 made the path name the owner's class and
check it on the way out, which left the owner's state as the one thing the path cannot carry.
BUG-192 shares the origin.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


class Counter:
    def __init__(self, start: int = 0) -> None:
        self.start = start

    def add(self, x: int) -> int:
        return x + self.start


def counter(start: int) -> Callable[[int], int]:
    return Counter(start).add


@dataclass
class Config:
    f: Callable[[int], int]


cfg = Config(f=Counter(100).add)
dumped = confarg.dump(cfg)
print(dumped)
# expected: a dump that reads back as Counter(100).add, or an error at dump()
# actual:   {'f': '__main__.Counter.add'}
print(confarg.from_dict(Config, dumped).f(1))
# expected: 101
# actual:   1

cfg = confarg.from_dict(Config, {"f": {"call": "__main__.counter", "start": 100}})
dumped = confarg.dump(cfg)
print(dumped)
# expected: a dump that reads back as Counter(100).add, or an error at dump()
# actual:   {'f': '__main__.Counter.add'}
print(confarg.from_dict(Config, dumped).f(1))
# expected: 101
# actual:   1
```

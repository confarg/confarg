---
filed: 2026-10-07
where:
  - src/confarg/_callable.py::_resolve_call_spec  # the stamp
  - src/confarg/_callable.py::_serialize_callable
  - tests/test_callables.py::TestSerialization  # test_a_stamped_spec_from_the_cli_dumps_plain_strings[call]
effort: S
risk: low
impact: behavior
severity: critical  # the dump re-runs the factory on read-back; a changed factory yields other values, silently
blocked_by: [BUG-193]
introduced_by: [PR-5]  # the initial version stamps every call: result with its spec
---
# BUG-191 — A `call:` result on a Callable field dumps as the call, not as what it produced

`dump()` writes the state of the built object, never the `call:` that produced a value
([the object dump writes state](../../architecture/design-decisions/the-object-dump-writes-state.md)).
A Callable field breaks the rule. `_resolve_call_spec` stamps the callable a `call:` returned with
the spec, and `_serialize_callable` writes the stamp back, so reading the dump re-runs the
factory. The stamp sits on the returned object itself, and a factory may return one it shares,
such as a module-level function. Every configuration holding that object then dumps the call too,
including one that named the function directly.

Fix direction: drop the stamp, so the result dumps through the rules for what it is: a
function as its path, a partial as `bind:`, a stamped `class:` instance as its spec. A result
with no configuration spelling must then be refused at `dump()`, which is BUG-193. Fixed alone,
this ticket would turn a closure's call spec into an unimportable path, hence `blocked_by`. The
CLI token test's `call` case dumps such a closure (`_make_adder`), and needs another target.

Origin: the initial version stamped `call:` results the way it stamped `class:` instances, so
that `dump()` could write a callable back as its spec. Nothing distinguished a spec that
describes the object (`class:`) from one that describes how to compute it (`call:`). The bug is
latent: the rule it breaks was only written down when FEAT-33 was declined.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


def shout(s: str) -> str:
    return s.upper()


def pick(name: str) -> Callable[[str], str]:
    return {"shout": shout}[name]


@dataclass
class Config:
    f: Callable[[str], str]


cfg = confarg.from_dict(Config, {"f": {"call": "__main__.pick", "name": "shout"}})
print(confarg.dump(cfg))
# expected: {'f': '__main__.shout'}
# actual:   {'f': {'call': '__main__.pick', 'name': 'shout'}}

other = confarg.from_dict(Config, {"f": "__main__.shout"})
print(confarg.dump(other))
# expected: {'f': '__main__.shout'}
# actual:   {'f': {'call': '__main__.pick', 'name': 'shout'}}
```

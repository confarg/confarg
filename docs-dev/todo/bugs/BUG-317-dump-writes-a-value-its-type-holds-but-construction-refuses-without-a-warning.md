---
filed: 2026-11-08
where:
  - src/confarg/_serialize.py::_serialize  # asks _holds, which reads the type as a type checker does
  - src/confarg/typedload/_holding.py::_holds
effort: M  # the design pass: where a leaf is asked whether it reads back, and what that costs per leaf
needs_design: true
risk: medium  # every leaf of every dump goes through it
impact: behavior  # a dump that does not load back warns
severity: critical  # the dump does not load back, with no warning
introduced_by: [PR-5, FEAT-51]  # PR-5: an int refusing a bool, its dump writing it as it is; FEAT-51: a date refusing a datetime's text
---

# BUG-317 — `dump()` writes a value its type holds but construction refuses without a warning

A `bool` in an `int` field and a `datetime` in a `date` field dump with no warning, and the dump does not load back: `C(n=True)` dumps as `{'n': True}`, which `build()` refuses.
A value its declared type does not hold warns that it will not read back ([a value its type does not hold](../../architecture/types/serialization.md#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it)), but `_holds` reads a type as a type checker does, for which a `bool` is an `int` and a `datetime` a `date`, while construction refuses both.
The same two values used as dict keys do warn ([a key that does not read back](../../architecture/types/serialization.md#a-key-that-does-not-read-back-is-written-with-a-warning)), since a key is asked whether it reads back, so the forensic dump's promise to warn where it will not ([the object dump is forensic](../../architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)) holds of a key and not of a value.

Fix direction, for the design pass: ask a leaf value whether it reads back, as a key is, at the cost of one reading per leaf; or narrow what `_serialize` asks to what construction takes, leaving `_holds` as it is, since construction of a built instance asks it too.

Origin: latent since the initial version (PR-5), whose `_coerce` refused a `bool` for an `int` and whose `_serialize` wrote a leaf as it stood; BUG-267 then added the warning, through a predicate that reads the type as a type checker does, and FEAT-51 made a `date` refuse a `datetime`'s text.

```python
import datetime
import warnings
from dataclasses import dataclass

import confarg


@dataclass
class C:
    n: int = 0
    d: datetime.date = datetime.date(2020, 1, 1)


for instance in (C(n=True), C(d=datetime.datetime(2020, 1, 1))):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dumped = confarg.dump(instance)
    print(dumped, "warnings:", len(caught))
    try:
        print(confarg.build(C, dumped))
    except confarg.exceptions.TypeCoercionError as e:
        print(f"{type(e).__name__}: {e}")
# expected: one ConfargWarning for each dump, saying the value will not read back
# actual:   {'n': True, 'd': '2020-01-01'} warnings: 0
#           TypeCoercionError: Cannot coerce bool True to int at 'n'
#           {'n': 0, 'd': '2020-01-01T00:00:00'} warnings: 0
#           TypeCoercionError: Cannot coerce str '2020-01-01T00:00:00' to date at 'd': a date is ISO 8601 text, such as '2021-02-03'
```

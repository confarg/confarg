---
filed: 2026-11-08
where:
  - src/confarg/_serialize.py::_serialize_dict  # warns of a key only where the key type is a union
  - src/confarg/_serialize.py::_warn_a_key_read_as_another
effort: S
risk: medium  # no test dumps a key its key type does not hold
impact: behavior  # a dump that read back as another dict warns
severity: critical  # the dump reads back as another value, with no warning
introduced_by: [BUG-267]  # warned of a value its declared type does not hold, never of a key
---

# BUG-314 — `dump()` writes a dict key its key type does not hold without a warning

A key that is no value of its dict's key type is written as it stands and reads back as another key, silently: `{'1': 'a'}` in a `dict[int, str]` field dumps as `{'1': 'a'}`, which builds `{1: 'a'}`.
A field's value its declared type does not hold warns that it will not read back (BUG-267), and a union key read back as another variant warns too (BUG-261, [a union key another variant reads](../../architecture/types/serialization.md#a-union-key-another-variant-reads-is-written-with-a-warning)), so only a key of a key type that is no union goes unsaid, against the forensic dump's promise to warn where it will not read back ([the object dump is forensic](../../architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).

Fix direction: ask every key, whatever its key type, whether `read_key` reads its written text back as itself, and warn as `_warn_a_key_read_as_another` does where it does not; the union case is then one instance of the rule.

Origin: latent since BUG-267, which made `dump()` warn of a value its declared type does not hold and left a dict's keys as `_serialize_leaf` writes them; BUG-261 added the key warning for a union key type alone.
BUG-307 shares the BUG-267 origin.

```python
import warnings
from dataclasses import dataclass, field

import confarg


@dataclass
class C:
    m: dict[int, str] = field(default_factory=dict)
    s: str = ""


for instance in (C(s=5), C(m={"1": "a"})):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dumped = confarg.dump(instance)
    print(dumped, "warnings:", len(caught))
print(confarg.build(C, confarg.dump(C(m={"1": "a"}))))
# expected: one ConfargWarning for each dump, the second saying the key '1' at 'm' reads back as the int 1
# actual:   {'m': {}, 's': 5} warnings: 1
#           {'m': {'1': 'a'}, 's': ''} warnings: 0
#           C(m={1: 'a'}, s='')
```

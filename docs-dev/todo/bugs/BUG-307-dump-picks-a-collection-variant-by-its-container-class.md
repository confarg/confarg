---
filed: 2026-11-05
where:
  - src/confarg/typedload/_holding.py::_variant_holds  # answers LIST, SET, FROZENSET and DICT by the container's class alone
  - src/confarg/typedload/_holding.py::first_holding_variant
  - src/confarg/_serialize.py::_serialize_union
effort: M
risk: medium  # first_holding_variant also hands construction a built instance, and the variant picked decides what dump() writes
impact: behavior  # a warning a user sees goes away
severity: minor  # a misleading message: the value is written and reads back
introduced_by: [BUG-31, BUG-267]  # BUG-31: a variant picked by shape; BUG-267: the warning that makes the pick visible
---

# BUG-307 — `dump()` picks a collection variant by its container class, and warns a value will not read back

A union of two collections of one class, `list[int] | list[str]`, writes a value by the first whatever its items are, so `dump(C(xs=['a']))` warns `Value at 'xs[0]' will not read back: its str is no value of int`, though the dump reads back equal.
`_variant_holds` answers a list, a set, a frozenset and a dict variant by `isinstance` on the container alone, so `_find_variant_type` stops at the first, and the items are serialized under an item type that does not hold them.
A generic struct variant already answers by its members (`_holds_members`), and `_holds` by the whole value; the collection kinds are the ones left.

Fix direction: the collection cases ask whether the variant holds the items too, preferring a variant holding the value whole, then falling back to the first of the container's class as today, so a value no variant holds keeps its warning.
`first_holding_variant` is asked of a built instance by construction too (`_instance_variant`), which takes only a struct or an unsupported leaf from it, so it should not change; a test should say so.

Origin: BUG-31 (PR-168) made `dump()` pick a variant by its shape, since a bare `isinstance` refused a parameterized generic and left a union holding one undumpable, and answered a collection by the concrete class construction builds, without its items.
The pick was silent then, the `str` item written as it is (run on BUG-267's parent: `{'xs': ['a']} []`); BUG-267 (PR-471), which writes a value its declared type does not hold as an `Any` node holds it, with a warning, made it a false warning.
So the wrong pick is latent in BUG-31, and the warning a regression of BUG-267, itself a bug fix: the two constraints meet in `_variant_holds`, which the warning trusts to have picked the variant that holds the value.

```python
import warnings
from dataclasses import dataclass

import confarg


@dataclass
class C:
    xs: list[int] | list[str] | None = None
    d: dict[str, int] | dict[str, str] | None = None
    t: set[int] | set[str] | None = None


for obj in (C(xs=["a"]), C(d={"k": "v"}), C(t={"a"})):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        d = confarg.dump(obj)
    print(obj, "->", d, [str(x.message) for x in w])
    print("   back ->", confarg.build(C, d))

# expected: no warning, each dump reads back equal
# actual:   C(xs=['a'], d=None, t=None) -> {'xs': ['a'], 'd': None, 't': None} ["Value at 'xs[0]' will not read back: its str is no value of int, the type it is declared as. It is written as an Any field holds it."]
#              back -> C(xs=['a'], d=None, t=None)
#           C(xs=None, d={'k': 'v'}, t=None) -> {'xs': None, 'd': {'k': 'v'}, 't': None} ["Value at 'd.k' will not read back: its str is no value of int, the type it is declared as. It is written as an Any field holds it."]
#              back -> C(xs=None, d={'k': 'v'}, t=None)
#           C(xs=None, d=None, t={'a'}) -> {'xs': None, 'd': None, 't': ['a']} ["Value at 't' will not read back: its str is no value of int, the type it is declared as. It is written as an Any field holds it."]
#              back -> C(xs=None, d=None, t={'a'})
```

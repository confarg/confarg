# BUG-4 — Stealing order does not match the documented rule

**Where:** `src/confarg/typedload/_coerce.py` (`_steal_order`) · **Filed:** 2026-09-12
**Effort:** M · **Risk:** high · **Impact:** config

Intended (confirmed by the maintainer, and what the tutorial in `examples/7_stealing_rule/`
teaches): `registered leaf > Enum > [float, int, bool, None] > str`. Implemented:
`Enum > other non-str types in declaration order > str`, with `None` and bool-vs-int handled
first — so the declaration order of the union decides what the documented rule fixes. Fix the
code, not the tutorial.
See [05-types-and-construction.md#stealing-rule](../../architecture/05-types-and-construction.md#stealing-rule).

```python
from dataclasses import dataclass
from decimal import Decimal
import confarg

confarg.register_leaf_type(Decimal, Decimal)

@dataclass
class A:
    v: int | Decimal = 0

@dataclass
class B:
    v: Decimal | int = 0

print("A:", repr(confarg.load(A, argv=["--v", "5"]).v))
print("B:", repr(confarg.load(B, argv=["--v", "5"]).v))
# expected: A: Decimal('5')   — a registered leaf outranks int whatever the order
#           B: Decimal('5')
# actual:   A: 5              — declaration order wins
#           B: Decimal('5')
# The documented float-before-int rule goes the same way: `int | float` gives 5,
# `float | int` gives 5.0.
```

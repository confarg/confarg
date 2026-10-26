---
filed: 2026-10-26
where:
  - src/confarg/_serialize.py::_variant_holds  # the arm for "a class, or parameterized over one"
  - src/confarg/typedload/_coerce.py::_coerce_type_ref  # the read-back check the dump must agree with
effort: S
risk: medium  # nothing pins the dump of a type[X] holding a foreign class; a mistake is silent in the dump alone
impact: behavior  # the dump gains the foreign-value warning
severity: minor  # the dump is refused loudly when read back
introduced_by: [BUG-31, BUG-267]  # BUG-31 wrote the isinstance(instance, type) arm, BUG-267 asked it of every field
---

# BUG-294 — The dump writes a class its `type[X]` field does not admit

A value its declared type does not hold is written as a foreign value, with a `ConfargWarning` ([serialization](../../architecture/types/serialization.md#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it)), so that a dump reads back as what it wrote ([a written file holds what its reader reads back](../../architecture/design-decisions/a-written-file-holds-what-its-reader-reads-back.md)).
For a `type[X]` field, `_serialize._variant_holds` asks only `isinstance(instance, type)`: any class is held, the dump writes its path with no warning, and reading the dump back refuses it, since `_coerce_type_ref` checks the class against `X`.

Fix direction: answer `type[X]` in `_variant_holds` with the same check `_coerce_type_ref` reads it back with, one predicate for both, which [FEAT-57](../features/FEAT-57-protocol-typed-fields.md) then extends to a Protocol `X` ([the Protocol plan](../plans/protocol-typed-fields.md#where-it-lives)).

Origin: latent since BUG-31, which picked a union variant by shape and answered a `type[X]` variant by `isinstance(instance, type)`, enough to tell it from the other variants; BUG-267 then asked `_variant_holds` whether any field holds its value, so the unchecked arm reached every `type[X]` field.

```python
import warnings
from dataclasses import dataclass

import confarg


class Base:
    pass


@dataclass
class C:
    t: type[Base]


warnings.simplefilter("always")
dumped = confarg.dump(C(int))
print("dump:", dumped)
try:
    print("load:", confarg.build(C, dumped))
except confarg.exceptions.ConfargError as e:
    print("load:", type(e).__name__, e)

# expected: a ConfargWarning naming 't', int and type[Base], then the dump
# actual:   dump: {'t': 'builtins.int'}  (no warning)
#           load: TypeCoercionError Class 'builtins.int' at 't' is not a subclass of __main__.Base.
```

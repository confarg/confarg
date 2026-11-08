---
filed: 2026-11-07
where:
  - src/confarg/_serialize.py::_object_form  # writes an instance by the serializer of the first registered class in its MRO
  - src/confarg/typedload/_coerce.py::_registered_leaf_of
effort: M  # the design pass: tag the instance, warn, or ask whether the serialized form reads back
needs_design: true
risk: medium  # every registered leaf's dump goes through it; a datetime and a WindowsPath must keep their form
impact: behavior  # a dump that read back as the parent becomes one that reads back as the subclass, or warns
severity: critical  # the dump reads back as another value, with no warning
introduced_by: [BUG-11]  # PR-127 serialized a registered leaf by isinstance; FEAT-51 kept it as the most specific registered class
---

# BUG-309 — `dump()` writes a registered leaf's unregistered subclass by its parent's serializer, silently

An instance of an unregistered subclass of a registered leaf is dumped by the parent's serializer, so it reads back as the parent: `SubPoint(x=3, y=4)` in a `Point` field dumps as `'3'`, which builds `Point(x=3)`, and nothing warns.
That breaks [one predicate answers both directions](../../architecture/types/serialization.md#serialization), "a value `dump()` writes is one construction can read back", and the forensic dump's promise to warn where it will not ([the object dump is forensic](../../architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).
An annotation reads through its own class's registration only, so `SubPoint` is a struct to construction ([a registration is one construction reaches](../../architecture/design-decisions/a-registration-is-one-construction-reaches.md#a-registration-is-one-construction-reaches)), while `_registered_leaf_of` reads an instance through the first registered class in its MRO: right for a `datetime`, registered itself, and a `WindowsPath`, which `Path(...)` rebuilds, wrong for a subclass whose constructor takes what the parent's coercion never builds.

Fix direction, for the design pass: write such an instance as the tagged dict its class builds from (`{class: pkg.SubPoint, x: 3, y: 4}`, which construction reads under a `Point` field today), warn that it will not read back, or test whether the serialized form coerces back to an equal value; an expression's writer (`_serialize.written_form`) shares `_object_form` and inherits the answer.
[A tagged leaf reads as the leaf it builds](../../architecture/expressions/values-and-references.md#a-tagged-leaf-reads-as-the-leaf-it-builds) reads a tag naming such a subclass as its dict, for the same reason.

Origin: latent since BUG-11, which serialized a registered leaf by the first registration the value is an `isinstance` of; FEAT-51 made it the most specific registered class (`_registered_leaf_of`) so a `datetime` is not written as a `date`, and kept a subclass no registration names written as its parent.

```python
import warnings
from dataclasses import dataclass

import confarg


@dataclass
class Point:
    x: int = 0


@dataclass
class SubPoint(Point):
    y: int = 0


confarg.register_leaf_type(Point, lambda v: Point(int(v)), serialize=lambda p: str(p.x))


@dataclass
class Config:
    origin: Point | None = None


with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    dumped = confarg.dump(Config(origin=SubPoint(3, 4)))
print(dumped, "warnings:", len(caught))
print(confarg.build(Config, dumped))
# expected: a dump that reads back as SubPoint(x=3, y=4), or a ConfargWarning saying it will not
# actual:   {'origin': '3'} warnings: 0
#           Config(origin=Point(x=3))
```

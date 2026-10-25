---
filed: 2026-10-25
where:
  - src/confarg/_typed_read.py::_read  # walks the tagged dict as a struct's fields
  - src/confarg/_typed_read.py::_read_leaf
  - src/confarg/typedload/_coerce.py::read_as_object  # reads no tag, so a lone leaf needs one threaded in
effort: M
risk: high  # the expression reading, every channel; no test reads a tagged leaf through an expression
impact: config  # an interpolation that reads the dict's text today reads the leaf's written form
severity: critical  # the interpolation is silent; the whole-value reference into a str field is loud
introduced_by: [BUG-16, BUG-246]  # PR-139 made the tagged spelling, PR-441 the object reading that skips it
---

# BUG-283 — A reference to a registered leaf written as a tagged dict reads the dict

A registered leaf that is a struct can be written as a dict whose union tag names its class ([an explicit tag opts a leaf back in](../../architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)), and construction builds it.
An expression reading it does not: `_typed_read._read` walks every dict as a struct's fields, so `${origin}` reads the dict as written where the same leaf written as `"3"` reads `Point(x=3)`, against [a typed leaf reads as its object](../../architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object).
An interpolation then writes the dict's text, silently, and a whole-value reference into a `str` field is refused.
Fix direction: read a dict carrying the tag at a taggable leaf, or at a union holding one, as a leaf, through the reading of the variant construction picks; `read_as_object` then needs the configuration's union tag, the half of REF-99's direction left out while no dict reached it.
A reference below the leaf, `${origin.x}`, reads the field the tagged dict holds today, which is the built `origin.x`, and keeps doing so.

Origin: latent since BUG-16, which let an explicit class tag build a registered leaf from its fields while every reference still read the value as written, so a tagged leaf interpolated as its dict text where a scalar one interpolated as its token.
BUG-246 made a reference read an Enum or registered leaf as the object construction builds, but only where `_read` reaches a leaf, and `_read` walks a dict before asking its type, so the tagged spelling was missed.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Point:
    x: int = 0


confarg.register_leaf_type(Point, lambda v: Point(int(v)), serialize=lambda p: str(p.x))


@dataclass
class Config:
    origin: Point | None = None
    label: str = ""


print(confarg.build(Config, {"origin": "3", "label": "at ${origin}"}))
print(confarg.build(Config, {"origin": {"class": "__main__.Point", "x": 3}, "label": "at ${origin}"}))
# expected: Config(origin=Point(x=3), label='at 3')
# actual:   Config(origin=Point(x=3), label="at {'class': '__main__.Point', 'x': 3}")
confarg.build(Config, {"origin": {"class": "__main__.Point", "x": 3}, "label": "${origin}"})
# expected: Config(origin=Point(x=3), label='3')
# actual:   confarg.exceptions.TypeCoercionError: Cannot coerce dict {'class': '__main__.Point', 'x': 3} to str at 'label'. The 'class' key picks the class to build from the keys beside it, and str is built from one value, not from keys. A 'call:' spec computes a value the field's type accepts.
```

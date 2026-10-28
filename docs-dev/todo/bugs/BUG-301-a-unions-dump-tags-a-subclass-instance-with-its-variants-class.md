---
filed: 2026-10-28
where:
  - src/confarg/_serialize.py::_serialize_union
effort: S
risk: low
impact: behavior  # a dump that failed to read back reads back
severity: major  # the dump of a valid value is refused on read-back, and no tag_policy avoids it
introduced_by: [PR-5]  # the initial version wrote both tags, the union's last
---

# BUG-301 — A union's dump tags a subclass instance with its variant's class

`dump()` of a union whose struct variant holds an instance of a subclass writes the subclass's tag (`_serialize_struct`'s `_tagged_struct` branch), then `_serialize_union` overwrites it with the variant's own class wherever it decides a tag is needed (`_needs_tag`, or `tag_policy="always"`).
The dump then names the base, which reads back as the base exactly ([class names the type it builds](../../architecture/design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds)) and refuses the subclass's fields; under a Protocol variant ([FEAT-57](../features/FEAT-57-protocol-typed-fields.md)) it would name the Protocol, which nothing builds.
Fix direction: the union's tag names the class the instance is written as, the one the struct's branch already wrote.

Origin: latent since PR-5, the initial version, whose `_serialize_struct` and `_serialize_union` each wrote a tag, the union's last.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Base:
    pass


@dataclass
class Impl(Base):
    name: str = "i"


@dataclass
class Other:
    k: int = 0


@dataclass
class C:
    g: Base | Other


data = confarg.dump(C(g=Impl()))
print(data)
print(confarg.build(C, data))
# expected: {'g': {'name': 'i', 'class': '__main__.Impl'}}
#           C(g=Impl(name='i'))
# actual:   {'g': {'name': 'i', 'class': '__main__.Base'}}
#           TypeCoercionError Unknown field(s) ['name'] for Base at 'g'. Valid fields: []
```

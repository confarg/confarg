---
filed: 2026-10-28
where:
  - src/confarg/_serialize.py::_serialize_union
  - src/confarg/typedload/_construct.py::_ambiguous_union_msg  # counts the owned key as no provided field, and offers the tag as remedy
effort: S
risk: medium  # the dump must then warn where the variant cannot be told apart
impact: behavior
severity: critical  # the dump writes a class path into the field, which reads back silently as the field's value
introduced_by: [BUG-102]  # PR-262, a real field wins the tag's spelling on read; the dump kept writing the tag
---

# BUG-302 — A union's dump overwrites the field that owns the tag's spelling

Where a variant's field is spelled like the union tag, that field owns the key ([real field wins](../../architecture/design-decisions/real-field-wins.md)), and no tag can select a variant there; yet `_serialize_union` writes the tag over the field's value whenever it decides a tag is needed (`_needs_tag`, or `tag_policy="always"`).
The field's value is lost, and it reads back as the class path, silently where the variants are otherwise told apart.
Fix direction: the dump writes no tag where the union reads the key as a member's (`tag_reading` answering `OWNED`), and warns, as for a foreign value, when the variants cannot be told apart without it.
The ambiguity refusal shares the blind spot: it lists the owned key as no provided field and offers the tag as its remedy.

Origin: BUG-102 made a real field win the tag's spelling when a value is read, and left the dump writing the tag; before it the key was the tag on both sides, so the field's value was lost either way.

```python
import warnings
from dataclasses import dataclass

import confarg


@dataclass
class Kinded:
    Kind: str = "x"


@dataclass
class Other:
    k: int = 0


@dataclass
class C:
    g: Kinded | Other


warnings.simplefilter("ignore")  # the shadowed-tag warning on read-back
data = confarg.dump(C(g=Kinded(Kind="field")), union_tag="Kind", tag_policy="always")
print(data)
print(confarg.build(C, data, union_tag="Kind"))
# expected: {'g': {'Kind': 'field'}}
#           C(g=Kinded(Kind='field'))
# actual:   {'g': {'Kind': '__main__.Kinded'}}
#           C(g=Kinded(Kind='__main__.Kinded'))
```

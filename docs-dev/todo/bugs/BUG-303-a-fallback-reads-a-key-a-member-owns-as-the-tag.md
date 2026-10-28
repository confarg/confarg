---
filed: 2026-10-28
where:
  - src/confarg/typedload/_construct.py::_construct_shadowed_subclass  # its try-each-subclass loop strips the key as a tag
  - src/confarg/typedload/_construct.py::_first_constructible  # a union's struct variant reads the key as its own tag
  - src/confarg/typedload/_construct.py::_construct_struct  # drops the tag-shaped key as extra, whoever owns it
effort: S
risk: medium  # the union fallback is shared by every refusal path a struct variant reaches
impact: config  # a value that builds today, its member's value dropped or imported, is refused
severity: critical  # the member's value is dropped silently, or imported as a class path
introduced_by: [BUG-102, BUG-103]  # PR-262 made the union's key a member's and left the variants reading it; PR-263 added the subclass loop
---

# BUG-303 — A fallback reads a key a member owns as the tag

Where a member owns the tag's spelling, the key is that member's value and no tag selects a class ([real field wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins)); construction says so, and warns, then its fallbacks read the key as the tag anyway.
`_construct_shadowed_subclass`, finding no subclass whose fields cover the keys, tries each subclass with `_construct_struct`, which drops the tag-shaped key as an extra: `{p: 1, Kind: anything}` under a `Base` whose subclass `Kinded` owns `Kind` builds `Plain(p=1)`, the value dropped, where `{p: 1}` is refused because no tag can select `Plain`.
`_construct_union`, the key read as a member's value since `Kinded` owns it, matches no variant by its fields and tries each with `_first_constructible`, whose `Other` reads the key as its own subclass tag and imports it.
`dump()` writes no tag where a member owns its spelling, and warns where the fields alone do not read back ([serialization](../../architecture/types/serialization.md#a-member-that-owns-the-tags-spelling-keeps-its-value)), so the dump no longer relies on these readings; a hand-written configuration still meets them.
Fix direction: a fallback under a position whose key a member owns never reads the key as the tag: the subclass loop and a struct variant's dispatch see it as the member's value it is, so a struct owning no such field refuses it as an unknown field.

Origin: BUG-102 (PR-262) made the union read the key as a member's value and route it to structural matching, and left the fallback constructing each variant through its own dispatch, which reads the key by the variant's own fields; BUG-103 (PR-263) added the try-each-subclass loop to `_construct_shadowed_subclass`, through `_construct_struct`, which has always dropped the key as the tag.
Both were bug fixes; both regressions of a reading they otherwise settled.

```python
import warnings
from dataclasses import dataclass

import confarg


@dataclass
class Base:
    pass


@dataclass
class Kinded(Base):
    Kind: str = "x"


@dataclass
class Plain(Base):
    p: int = 0


@dataclass
class Other:
    q: int = 0


@dataclass
class S:
    g: Base


@dataclass
class U:
    g: Kinded | Other


@dataclass
class Sub(Other):
    p: int = 0


warnings.simplefilter("ignore")  # the read says the key is the member's value
print(confarg.build(S, {"g": {"p": 1, "Kind": "anything"}}, union_tag="Kind"))
print(confarg.build(U, {"g": {"p": 1, "Kind": "__main__.Sub"}}, union_tag="Kind"))
# expected: both refused, as {"g": {"p": 1}} is: a member owns 'Kind', so no tag selects a class
# actual:   S(g=Plain(p=1))
#           U(g=Sub(q=0, p=1))
```

---
filed: 2026-10-01
where:
  - src/confarg/typedload/_construct.py::_struct_matches_value
effort: S
risk: medium
impact: behavior
severity: minor  # workaround: spell the tag explicitly
introduced_by: [PR-5]  # _struct_matches_value's unconditional `k != union_tag`
---
# BUG-107 — A real field named like the tag, nested inside a union variant, is stripped by the type check

`_struct_matches_value`, which `_value_matches_type` asks when a union's structural
disambiguation checks a variant's nested struct value, drops the tag-shaped key
unconditionally (`keys = {k for k in value if k != union_tag}`). Its sibling
`_disambiguate_struct` drops it only when no variant owns the spelling, through the canonical
`_union_tag_shadowed` (BUG-102). So a real field spelled like a custom tag, one level below a
union variant, is read as the tag. The variant whose nested struct needs that field then fails
to match, and the union reports an ambiguity it should have resolved. The function also
duplicates `_structurally_matches`. Fix direction: drop the tag only when
`_union_tag_shadowed` says no member owns it, and share the coverage test with
`_structurally_matches`. See
[real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins).

Origin: latent since the initial version (PR-5), which dropped the tag-shaped key in every
structural check. BUG-102's fix taught `_disambiguate_struct` to keep a real field spelled like the
tag, through `_union_tag_shadowed`, and left this sibling on the unconditional drop: the
reproduction fails the same way before and after that fix.

```python
from dataclasses import dataclass
import confarg


@dataclass
class A:
    kind: int


@dataclass
class B:
    other: int


@dataclass
class Wa:
    v: A


@dataclass
class Wb:
    v: B


@dataclass
class Root:
    w: Wa | Wb


for tag in ("zz", "kind"):
    try:
        print(tag, confarg.load(Root, argv=["--w.v.kind", "1"], env={}, union_tag=tag))
    except Exception as e:
        print(tag, type(e).__name__, str(e).splitlines()[0])

# expected: both lines print Root(w=Wa(v=A(kind=1)))
# actual:
#   zz Root(w=Wa(v=A(kind=1)))
#   kind AmbiguousUnionError Ambiguous union at 'w': cannot distinguish between Wa, Wb.
```

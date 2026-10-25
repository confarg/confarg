---
filed: 2026-10-25
where:
  - src/confarg/typedload/_construct.py::_first_constructible  # catches ConfargError, AmbiguousUnionError among them
  - src/confarg/typedload/_construct.py::_construct_union_leaf
effort: M
needs_design: true  # whether an ambiguity met inside a variant ends the walk, as it does at the union's own position
risk: high  # the union walk is construction's, under every channel and front-end
impact: config  # a configuration an ambiguous item builds as another variant today would be refused
severity: critical  # the value is built as a variant the user did not choose, with no error
introduced_by: [PR-5]
---

# BUG-288 — An ambiguity inside a union variant lets the next variant take the value

A union whose variant holds an ambiguous union, `list[Cat | Dog] | list[dict[str, str]]`, builds `[{'name': 'Rex'}]` as the dict variant: the item `{'name': 'Rex'}` cannot tell `Cat` from `Dog`, the list variant refuses it with an `AmbiguousUnionError`, and the walk tries the next variant, which takes it.
The same item at a lone `Cat | Dog` field is refused as ambiguous ([construction](../../architecture/types/construction.md#construction)), and the refusal suggests the tag that would settle it.
Where no later variant takes the value, the ambiguity survives only as one variant's line under a `TypeCoercionError` (`list[Cat | Dog]: ambiguous union at 'pets[0]': …`), no longer the `AmbiguousUnionError` a caller may catch.

Fix direction, for the design pass: whether `_first_constructible` lets an `AmbiguousUnionError` through, ending the walk as the union's own structural rung does, or records it as a refusal, with the variant that would have taken the value named in the message; the scalar walk does not raise one, so the struct, fixed-sequence and collection rungs are the sites.
Precedents to run then: pydantic's smart-mode union, which tries every member and keeps the exact match *(inferred)*, and cattrs, which refuses a union of classes it cannot disambiguate at structuring-hook creation *(inferred)*.

Origin: latent since the initial version (PR-5), whose union construction tried each variant under `except (ConfargError, TypeError)`, a catch REF-52 (#321) later gathered into `_first_constructible`; `AmbiguousUnionError` is a `ConfargError`, so a variant's ambiguity reads as its refusal.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Cat:
    name: str = ""


@dataclass
class Dog:
    name: str = ""


@dataclass
class Pets:
    pets: list[Cat | Dog] | list[dict[str, str]] = None


@dataclass
class Pet:
    pet: Cat | Dog | None = None


print(confarg.build(Pets, {"pets": [{"name": "Rex"}]}))
# expected: AmbiguousUnionError at 'pets[0]', as for the same item at a lone union field
# actual:   Pets(pets=[{'name': 'Rex'}])
confarg.build(Pet, {"pet": {"name": "Rex"}})
# AmbiguousUnionError: Ambiguous union at 'pet': cannot distinguish between Cat, Dog.
```

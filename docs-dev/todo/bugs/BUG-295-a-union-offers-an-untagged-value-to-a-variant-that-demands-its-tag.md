---
filed: 2026-10-26
where:
  - src/confarg/typedload/_construct.py::_construct_struct_dispatch
  - src/confarg/cli/_build.py::_collect_struct_specs
  - src/confarg/_default_layer.py::_struct_built_from
  - src/confarg/_types.py::_direct_struct_subclasses
  - src/confarg/typedload/_construct.py::_disambiguate_struct  # leaves such a variant out of the untagged match
effort: M
risk: high  # union disambiguation is shared by every channel and front-end
impact: config  # a value ambiguous today starts building the other variant
severity: minor  # tagging the other variant works around it
introduced_by: [PR-63]  # made a struct with subclasses demand its tag, and left it in the untagged match
---

# BUG-295 — A union offers an untagged value to a variant that demands its tag

A struct with subclasses is built only through the union tag ([no implicit subclass inference](../../architecture/design-decisions/no-implicit-subclass-inference.md#no-implicit-subclass-inference)), yet union disambiguation still matches it structurally against an untagged value.
So `{}` under `Base | AllDefaults`, where `Base` is an ABC with a subclass, is ambiguous between a variant that cannot be built from it and one that can, and the remedy the message offers, `'class': 'Base'`, builds the abstract `Base` exactly ([class names the type it builds](../../architecture/design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds)), which is refused.

Fix direction, decided while designing Protocol fields ([the Protocol plan](../plans/protocol-typed-fields.md#where-it-lives)): one predicate, `_types._demands_tag`, answers whether a struct requires its tag, asked by the three sites that ask `_direct_struct_subclasses` today and by `_disambiguate_struct`, which leaves such a variant out of the untagged match.
`{}` then builds `AllDefaults`, and a value no other variant takes gets the union refusal, whose line for `Base` says it demands the tag ([a union refusal names each variant's reason](../../architecture/types/construction.md#a-union-refusal-names-each-variants-reason)).
[FEAT-57](../features/FEAT-57-protocol-typed-fields.md) extends the predicate to Protocols.
The fix must also cover a variant whose custom `union_tag` a subclass-only field owns ([real field wins](../../architecture/design-decisions/real-field-wins.md)): the tag is not demanded there, yet the variant is still built only through the subclass its fields select, so it should match an untagged value only when that selection takes it, never `{}` by its own empty fields.

Origin: latent since PR-63, which removed implicit subclass inference and made `_construct_struct_dispatch` demand the tag of a struct with subclasses, but left union disambiguation matching that struct by its own fields.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

import confarg


class Base(ABC):
    @abstractmethod
    def greet(self) -> str: ...


@dataclass
class Impl(Base):
    name: str = "i"

    def greet(self) -> str:
        return self.name


@dataclass
class AllDefaults:
    k: int = 0


@dataclass
class C:
    g: Base | AllDefaults


for data in ({"g": {}}, {"g": {"class": "__main__.Base"}}):
    try:
        print(data, "->", confarg.build(C, data))
    except Exception as e:
        print(data, "->", type(e).__name__, e)

# expected: {'g': {}} -> C(g=AllDefaults(k=0))
# actual:   {'g': {}} -> AmbiguousUnionError Ambiguous union at 'g': cannot distinguish between Base, AllDefaults.
#             Base: (no fields)
#             AllDefaults: optional: k
#           Provided fields: (none)
#           To select a variant add a 'class' field, e.g. 'class': 'Base'. The field name can be changed via the union_tag= parameter.
#           and the remedy it offers:
#           {'g': {'class': '__main__.Base'}} -> TypeCoercionError Class '__main__.Base' at 'g' cannot be built with no arguments: Can't instantiate abstract class Base without an implementation for abstract method 'greet'. Supply the class's fields as keys beside the tag.
```

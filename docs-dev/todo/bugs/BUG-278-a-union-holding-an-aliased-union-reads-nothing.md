---
filed: 2026-10-24
where:
  - src/confarg/_types.py::_union_args  # a variant that resolves to a union is kept whole
  - src/confarg/_types.py::_union_args_no_none
effort: M  # every reader of a union's variants: construction, registration, completion, help, the typed merge walk
risk: medium
impact: behavior
severity: major  # close call with minor: writing the alias's union out in the annotation works around it
introduced_by: [PR-5]  # the initial union walk takes get_args() without resolving its variants
---

# BUG-278 — A union holding an aliased union reads nothing

`type IntOrFloat = int | float` makes `IntOrFloat | bool` a union of two variants, one of which is itself a union: typing flattens a nested union written inline, not one behind a `TypeAliasType`.
The union walk takes the variants as they are, and the aliased variant resolves to a union no leaf rung reads, so every value is refused — a token, a file's int, a float — with a message calling the variant "no leaf type confarg reads", and naming it `Union` on 3.14 (the one way `_construct._variant_name` meets a union, [BUG-277](BUG-277-a-refusal-names-a-union-union-on-python-3-14.md)).
[Wrappers are transparent](../../architecture/types/introspection.md#wrappers-are-transparent) promises a `TypeAliasType` is unwrapped in any nesting; `_resolve_type` unwraps the variant but nothing flattens what it yields.
Fix direction: flatten a variant that resolves to a union where the variants are read (`_union_args`), so `IntOrFloat | bool` is `int | float | bool` to every walk.
Found while weighing the review of BUG-252's fix.

Origin: latent since the initial version (PR-5), whose union walk read `get_args()` of the resolved union without resolving the variants; it refuses `--x 3` there as now.

```python
from dataclasses import dataclass

import confarg

type IntOrFloat = int | float


@dataclass
class C:
    x: IntOrFloat | bool = 0


@dataclass
class P:
    x: int | float | bool = 0


for cls in (C, P):
    try:
        print(confarg.load(cls, argv=["--x", "3"]))
    except Exception as e:
        print(f"{type(e).__name__}: {e}")

# expected: C(x=3), as P(x=3)
# actual:
# TypeCoercionError: Cannot coerce str '3' to IntOrFloat | bool at 'x'; IntOrFloat is no leaf type confarg reads
# P(x=3)
# on 3.14 the first line reads: Cannot coerce str '3' to Union | bool at 'x'; Union is no leaf type confarg reads
```

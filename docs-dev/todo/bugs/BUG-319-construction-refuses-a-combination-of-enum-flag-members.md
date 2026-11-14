---
filed: 2026-11-09
where:
  - src/confarg/typedload/_coerce.py::_coerce_enum_value
  - src/confarg/typedload/_coerce.py::_enum_choices  # what --help lists
effort: M  # the spellings each channel takes, and what --help lists, are a design pass
needs_design: true
risk: low
impact: behavior  # a value that was refused starts reading
severity: major  # a legal value is refused, and no spelling reads as it
introduced_by: [PR-46]
---

# BUG-319 — Construction refuses a combination of `enum.Flag` members

`Perm.R | Perm.W` is a legal value of a `Perm` field, and no spelling reads as it: `3`, `R|W` and `--f 3` are all refused, as is `Perm(0)`, for `Flag` and `IntFlag` alike.
`_coerce_enum_value` looks up a name, then walks `for member in tp`, which yields single-bit members only.
`dump()` writes `3`, and warns that it will not read back ([a leaf is asked whether it reads back](../../architecture/types/serialization.md#a-leaf-is-asked-whether-it-reads-back)).

Fix direction, for the design pass: read an integer through `tp(value)` for a `Flag`, and decide whether the CLI and the environment take `3`, `R|W` or both, what `--help` lists as choices, and how a `Literal` over a `Flag` reads.
pydantic, msgspec and cattrs all dump `3` and read it back as `<Perm.R|W: 3>`, for `Flag` and `IntFlag` (run).

Origin: latent since PR-46, which gave `_coerce_enum_value` its walk over the members to read a value by its text, for the CLI integrations; a `Flag` combination is no member of that walk.

```python
import enum
from dataclasses import dataclass

import confarg


class Perm(enum.Flag):
    R = 1
    W = 2


@dataclass
class C:
    f: Perm = Perm.R


print(confarg.build(C, {"f": 3}))
# expected: C(f=<Perm.R|W: 3>)
# actual:   TypeCoercionError: Cannot coerce int 3 to Perm at 'f'. Valid members: 'R' ('1'), 'W' ('2')
```

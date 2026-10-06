---
filed: 2026-10-06
where:
  - src/confarg/typedload/_construct.py::_construct_struct  # the final tp(**kwargs) call
effort: S
risk: low
impact: behavior
severity: minor  # nothing was supplied, and the answer is a raw TypeError rather than MissingFieldError
introduced_by: [PR-5]  # the initial version's root construction calls tp() on an empty dict
---
# BUG-184 — A struct root that refuses an empty call escapes `build()` as a `TypeError`

A class whose `__init__` defaults every parameter but refuses an empty call, `UUID` among
them, raises its own `TypeError` out of `load()` when it is the *root* and no channel supplied
it. As a *field* it raises `MissingFieldError`: BUG-18 settled that the "built from `{}`"
shortcut is a guess, and a `TypeError` out of it means the value is missing
([construction](../../architecture/types/construction.md#structs-collections-and-defaults)).
Fix direction: the root takes the same rule as the field, so a missing root is reported as one
(the remedy is the root's, as for a scalar root nothing supplied).

Origin: latent since the initial version (PR-5), which built a struct root from the empty merged
dict by calling its constructor with no arguments. BUG-18 fixed the same guess for a missing
field and left the root, which reaches the constructor through `_construct_struct` without
taking the field branch. The reproduction fails the same way at PR-5 and at every revision since.

```python
from dataclasses import dataclass
from uuid import UUID

import confarg


@dataclass
class Config:
    ident: UUID


for target in (Config, UUID):
    try:
        confarg.load(target, argv=[], env={})
    except Exception as e:
        print(type(e).__name__, e)

# expected: a MissingFieldError for both
# actual:
#   MissingFieldError Missing required field 'ident' of type <class 'uuid.UUID'>. Set it via CLI (--ident), environment variable, or config file.
#   TypeError one of the hex, bytes, bytes_le, fields, or int arguments must be given
```

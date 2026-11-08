---
filed: 2026-10-24
where:
  - src/confarg/_api.py::_named
effort: S
risk: low  # the message only
impact: none
severity: minor  # a misleading message: the refusal names no type the user wrote
introduced_by: [BUG-248]  # PR-460, which wrote _named with a __name__ fallback
---

# BUG-277 — A refusal names a union `Union` on Python 3.14

Since 3.14 `int | str` is an instance of `typing.Union`, whose `__name__` is `Union`, so every message that names a type by `getattr(tp, "__name__", repr(tp))` names a union `Union` there, where 3.12 and 3.13, finding no `__name__`, printed it as written.
`_api._named` does, for the nesting refusal of a root union target; the other sites spelling a type that way are listed in [REF-97](../refactors/REF-97-how-a-message-names-a-type-is-spelled-by-hand.md), and any of them a union reaches says `Union` too *(inferred)*.
`_construct._variant_name` names a union's variants, which `_types._union_args` reads flat since BUG-278, so it meets no union any more.
Fix direction: name the type through `_types._spell_type`, which spells a union by its variants on every Python, as REF-97 plans for every site.
Found while fixing BUG-252, whose refusal was routed through `_spell_type` for this reason.

Origin: BUG-248 wrote `_named` with the `__name__` fallback the other sites use, which prints a union as written only where a union has no `__name__`, before 3.14.
Latent on 3.12 and 3.13; whether 3.14 was in the CI matrix when BUG-248 landed was not checked.

```python
import sys
from typing import Any

import confarg

deep = "leaf"
for _ in range(70):
    deep = {"k": deep}

try:
    confarg.build(int | dict[str, Any], {"__root__": deep})
except Exception as e:
    print(sys.version_info[:2], f"{type(e).__name__}: {e}")

# expected (3.12): (3, 12) ConfargError: Cannot build int | dict[str, typing.Any]: it nests deeper than 64 levels, at 'k.k.k ... k.k' (65 levels).
# actual (3.14):   (3, 14) ConfargError: Cannot build Union: it nests deeper than 64 levels, at 'k.k.k ... k.k' (65 levels).
```

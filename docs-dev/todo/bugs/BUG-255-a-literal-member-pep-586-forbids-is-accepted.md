---
filed: 2026-10-18
where:
  - src/confarg/_types.py::_literal_values
  - src/confarg/typedload/_coerce.py::_coerce_literal_value
effort: S
needs_design: true  # where the refusal happens (reading the type, construction, dump) and whether the adapters refuse it at registration
risk: low
impact: config  # a field annotated Literal[1.0] stops building
severity: minor  # invalid input answered with a value; every type checker already flags the annotation
introduced_by: [PR-5]  # the initial Literal coercion read get_args() unchecked
---

# BUG-255 — A `Literal` member PEP 586 forbids is accepted

PEP 586 allows a `Literal` member to be an `int`, `str`, `bytes`, `bool`, an `Enum` member or `None`, and nothing else; `typing` does not check it at runtime, and neither does confarg.
So `x: Literal[1.0, 2.5]` builds from `--x 1`, matching the float member through `float`'s coercer, though `ty`, mypy and pyright all reject the annotation.
Fix direction: refuse a member of any other type with a confarg error naming the field and the member, at the one place the members are read (`_literal_values`), so construction, dump and the adapters' registration all inherit it.
Found while settling BUG-154, whose fix leaves `Literal` matching alone for that reason.

Origin: latent since the initial version (PR-5), whose Literal coercion took `get_args()` as the member list without checking a member's type.
No revision since has revisited it.

```python
from dataclasses import dataclass
from typing import Literal

import confarg


@dataclass
class L:
    x: Literal[1.0, 2.5] = 2.5  # rejected by every type checker


print(confarg.load(L, argv=["--x", "1"], env={}))
# expected: a confarg error naming the float member 1.0 at 'x'
# actual:   L(x=1.0)
```

---
filed: 2026-10-10
where:
  - src/confarg/typedload/_coerce.py::_coerce_registered
  - src/confarg/__init__.py::register_leaf_type
effort: S
risk: medium  # nothing covers a non-class key
impact: behavior
severity: minor  # a raw exception, with a workaround: annotate the supertype instead
introduced_by: [PR-37]  # the instance passthrough, `isinstance(value, tp)`
---

# BUG-222 — A registered `NewType` crashes with a raw `TypeError`

`register_leaf_type` accepts any key, and `_coerce_registered` passes an instance through with `isinstance(value, tp)` before its `try`.
A `NewType` is not a class, so every value for such a field crashes with Python's own `TypeError` instead of being coerced, in every channel.
An unregistered `NewType` field is refused too, with a confarg error (`Unsupported leaf type`), so registration is the obvious thing a user tries next.

Fix direction: either unwrap `NewType` to its supertype as introspection already does for `Final` ([wrappers are transparent](../../architecture/types/introspection.md#wrappers-are-transparent)), or have `register_leaf_type` refuse a non-class with a clear error.
A generic alias such as `tuple[int, int]` is accepted by registration too and then silently ignored, because shape dispatch claims the field first; refusing non-classes would cover both.

Origin: latent since PR-37, which added registration and the instance passthrough on the assumption that every registered key is a class.

```python
from dataclasses import dataclass
from typing import NewType

import confarg

UserId = NewType("UserId", int)
confarg.register_leaf_type(UserId, lambda v: UserId(int(v)))


@dataclass
class Config:
    user: UserId


print(confarg.from_dict(Config, {"user": "3"}))
# expected: Config(user=3)  (or a confarg error at registration)
# actual:   TypeError: isinstance() arg 2 must be a type, a tuple of types, or a union
```

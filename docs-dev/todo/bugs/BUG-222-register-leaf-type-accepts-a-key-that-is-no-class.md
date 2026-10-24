---
filed: 2026-10-10
where:
  - src/confarg/__init__.py::register_leaf_type
  - src/confarg/typedload/_coerce.py::_registered_leaf_of
effort: S
needs_design: true  # unwrap NewType to its supertype, or refuse every key that is no class
risk: medium  # nothing covers a non-class key
impact: behavior
severity: minor  # the registration is silently ignored; annotating the supertype works
introduced_by: [PR-37]  # register_leaf_type, which took any key
---

# BUG-222 — `register_leaf_type` accepts a key that is no class

`register_leaf_type` accepts any key, and assumes it is a class.
A generic alias such as `tuple[int, int]` is accepted and then silently ignored: shape dispatch claims the field before the registry is asked, so the coercion registered for it never runs.
A `NewType` crashed every value with Python's own `TypeError`, from the instance passthrough's `isinstance(value, tp)`, until FEAT-51 replaced that test with `_registered_leaf_of`, which looks the value's class up in the registry; it now builds and dumps, by accident rather than by design, and nothing tests it.
Fix direction: either unwrap `NewType` to its supertype as introspection already does for `Final` ([wrappers are transparent](../../architecture/types/introspection.md#wrappers-are-transparent)) and support it on purpose, or have `register_leaf_type` refuse a key that is no class with a clear error; refusing would cover the generic alias too.

Origin: latent since PR-37, which added registration on the assumption that every registered key is a class.

```python
from dataclasses import dataclass

import confarg

confarg.register_leaf_type(tuple[int, int], lambda v: tuple(int(x) for x in v.split("x")))


@dataclass
class C:
    size: tuple[int, int] = (0, 0)


try:
    print(confarg.from_dict(C, {"size": "3x4"}))
except Exception as e:
    print(type(e).__name__, e)
# expected: C(size=(3, 4))  (or a confarg error at registration)
# actual:   TypeCoercionError Cannot construct tuple at 'size': expected list, tuple, or dict with integer keys, got str '3x4'
```

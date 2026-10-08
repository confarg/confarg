---
filed: 2026-10-08
where:
  - src/confarg/typedload/_coerce.py::_coerce_leaf
effort: S
risk: low
impact: behavior
severity: minor
introduced_by: [PR-5]  # _coerce_leaf enumerated one branch per scalar type, and Any never got one
---
# BUG-212 — An Any dict-key annotation is refused as an unsupported leaf

`dict[Any, Any]` and `dict[Any, K]` do not build: `_construct_dict` coerces every key through `_coerce_leaf`, and `_coerce_leaf` has no branch for `Any`, so the key itself raises `Unsupported leaf type typing.Any` — before the value is ever asked. BUG-187's fix direction ("give a bare `dict` the DICT shape with `Any` keys and values, as `dict[Any, Any]` already has") assumed this worked; it never did. Fix direction: `Any` is the one leaf every value holds — pass the value through, as `construct()`'s `ANY` branch does
([introspection](../architecture/types/introspection.md#shape-dispatch)).

Origin: latent since the initial version (PR-5), whose `_coerce_leaf` enumerated one branch per scalar type and none for `Any`; a dict's key coercion asks it directly, without the shape dispatch that handles `ANY` elsewhere. Shares its origin with [BUG-187](BUG-187-a-bare-dict-annotation-is-refused-as-an-unsupported-leaf.md).

```python
from dataclasses import dataclass
from typing import Any

import confarg


@dataclass
class Config:
    d: dict[Any, Any]


print(confarg.build(Config, {"d": {"x": 1}}))
# expected: Config(d={'x': 1})
# actual:   TypeCoercionError: Unsupported leaf type typing.Any at 'd'
```

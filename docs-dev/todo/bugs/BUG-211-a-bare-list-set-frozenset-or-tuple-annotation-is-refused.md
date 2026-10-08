---
filed: 2026-10-08
where:
  - src/confarg/_types.py::_is_list
  - src/confarg/_types.py::_is_set
  - src/confarg/_types.py::_is_frozenset
  - src/confarg/_types.py::_is_tuple
  - src/confarg/_types.py::_is_varlen_collection  # a bare tuple must read as variadic
  - src/confarg/_types.py::_tuple_types
effort: S
risk: low
impact: behavior
severity: minor
introduced_by: [PR-5]  # the shape predicates matched the generic origin, which a bare class has none of
---
# BUG-211 — A bare list, set, frozenset or tuple annotation is refused as an unsupported leaf

The same defect as [BUG-187](BUG-187-a-bare-dict-annotation-is-refused-as-an-unsupported-leaf.md), on the other four collections: `get_origin` of a bare class is `None`, so none of the shape predicates match it, `_type_kind` names it `LEAF`, and construction raises. A bare `tuple` carries an extra trap: a naive predicate fix alone would read it as a fixed zero-length tuple, where PEP 484 reads it as `tuple[Any, ...]`. Fix direction: read every bare collection as its `Any`-parameterized form, in the one predicate each shape question already goes through
([introspection](../architecture/types/introspection.md#shape-dispatch)).

Origin: latent since the initial version (PR-5), whose shape predicates matched the generic origin alone; a bare class has no origin to match, so it was never given a shape.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    xs: list


print(confarg.build(Config, {"xs": [1, "a"]}))
# expected: Config(xs=[1, 'a'])
# actual:   TypeCoercionError: Unsupported leaf type <class 'list'> at 'xs'
```

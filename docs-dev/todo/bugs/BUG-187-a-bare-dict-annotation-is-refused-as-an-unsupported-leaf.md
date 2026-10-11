---
filed: 2026-10-06
where:
  - src/confarg/typedload/_coerce.py::_type_kind  # `_is_dict` matches dict[...] and mappings, not a bare `dict`
effort: S
risk: low
impact: behavior
severity: minor
introduced_by: [PR-5]  # the initial version: a bare `dict` was never given the DICT shape
---
# BUG-187 — A bare `dict` annotation is refused as an unsupported leaf

A field annotated with the bare `dict` cannot be built from a mapping. `dict[str, Any]` and
`dict[str, int]` build, so the annotation is a standard one the docs promise to support
([no custom types required](../../architecture/design-decisions/no-custom-types-required.md)). The
bare form falls through to the leaf path, which has no coercion for `dict`, and raises. Fix
direction: give a bare `dict` the DICT shape with `Any` keys and values, as `dict[Any, Any]`
already has.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    d: dict


print(confarg.build(Config, {"d": {"x": 1}}))  # expected: Config(d={'x': 1}); actual: TypeCoercionError
```

Actual output, from the parent revision (`okssqmllxtos`), run as `repro_bare_dict.py`:

```text
confarg.exceptions.TypeCoercionError: Unsupported leaf type <class 'dict'> at 'd'
```

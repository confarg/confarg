---
filed: 2026-10-17
where:
  - src/confarg/typedload/_construct.py::_construct_union_by_tag
effort: S
risk: low
impact: behavior
severity: minor  # a refusal of invalid input, with a message that lists nothing
introduced_by: [PR-5]  # the initial union-tag refusal listed the struct variants, which may be none
---

# BUG-252 — A class tag on a union with no struct variant lists no candidate

A dict carrying the union tag on a union none of whose variants is a struct is refused with "Expected a subclass of one of: []": the message lists the struct variants a tag could select, and there are none.
Fix direction: when no variant takes a tag, say so, and name the `call:` spec that computes a value the union holds, as `_construct_scalar` does for a non-struct field ("{T} accepts no struct, so the tag cannot select one").
Found while settling BUG-153, where a union of field-less plain classes reached the same message (no longer: such a class is a struct now).

Origin: latent since the initial version (PR-5), whose tag refusal listed the struct variants and never met a union holding none.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    x: int | str = 0


try:
    confarg.build(Config, {"x": {"class": "pathlib.Path"}})
except Exception as e:
    print(f"{type(e).__name__}: {e}")

# expected: a refusal saying int | str holds no struct a tag could select, naming the call: spec
# actual:   TypeCoercionError: Class 'pathlib.Path' at 'x' is not compatible with any union variant.
#           Expected a subclass of one of: []
```

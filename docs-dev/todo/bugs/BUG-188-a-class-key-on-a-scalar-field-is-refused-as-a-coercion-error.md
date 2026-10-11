---
filed: 2026-10-06
where:
  - src/confarg/typedload/_construct.py::_construct_scalar
effort: S
risk: low
impact: behavior
severity: minor
introduced_by: unknown  # searched: _construct_scalar and _coerce_int_value; the scalar path never reads the union tag, so the mapping falls to the leaf coercion. Not bisected.
---
# BUG-188 — A class key on a scalar field is refused as a coercion error

A `class:` key on a field whose annotation is a scalar (`int`, `str`) is refused with the generic
leaf message, `Cannot coerce dict {...} to int`. That message names neither the class nor the
spec that would build a value. FEAT-29 settled that a class tag on a typed field names a subclass
of the annotation, and that a class it does not accept is refused with a pointer to `call:`
([class names a subclass](../../architecture/design-decisions/class-names-a-subclass-call-computes.md)).
A scalar field has no struct to name a subclass of, so the refusal stays, but it should say what
the key is and where a value can come from.

Origin: latent. The scalar path has never read the union tag, so the mapping goes straight to
leaf coercion; the case was missed when the tag was made a struct-only rule.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Other:
    z: int = 3


@dataclass
class Config:
    n: int = 0


# expected: a refusal naming the 'class' key and pointing to a 'call:' spec
# actual:   "Cannot coerce dict {'class': ...} to int at 'n'"
print(confarg.build(Config, {"n": {"class": f"{__name__}.Other", "z": 1}}))
```

Actual output, from the parent revision (`vkqxmkxr`), run as `repro_bug188.py`:

```text
confarg.exceptions.TypeCoercionError: Cannot coerce dict {'class': '__main__.Other', 'z': 1} to int at 'n'
```

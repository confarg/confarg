---
filed: 2026-10-05
where:
  - src/confarg/typedload/_construct.py::_construct_single_variant_union
effort: S
risk: medium
impact: behavior
---
# BUG-159 — An optional field hides its value's own coercion error

`_construct_single_variant_union` catches any `TypeCoercionError` or `MissingFieldError` from
its one variant and raises a generic "Cannot coerce … To set this field to None, pass 'none'"
in its place, cause suppressed. For a value that could never have meant none — a dict, a list —
the remedy is beside the point and the real failure is lost: the inner path and reason a plain
`Inner` field reports (`inner.q`), the missing field's name, or a callable spec's own refusal.
Fix direction: let the variant's error through unless the value is a scalar token, where the
none-word remedy can apply. pydantic reports an `Optional[Model]` failure at the inner location
the same way it reports the plain model's. See
[messages live on exceptions](../../architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it).

```python
from dataclasses import dataclass

import confarg


@dataclass
class Inner:
    q: int = 0


@dataclass
class Plain:
    inner: Inner


@dataclass
class Opt:
    inner: Inner | None = None


for cls in (Plain, Opt):
    try:
        confarg.build(cls, {"inner": {"q": "notint"}})
    except confarg.exceptions.ConfargError as e:
        print(f"{cls.__name__:5}:", type(e).__name__, e)

# expected: Opt reports what Plain reports
# actual:
#   Plain: TypeCoercionError Cannot coerce str 'notint' to int at 'inner.q'
#   Opt  : TypeCoercionError Cannot coerce dict {'q': 'notint'} to Inner at 'inner'. To set this field to None, pass 'none' or 'null'.
```

---
filed: 2026-10-26
where:
  - src/confarg/typedload/_construct.py::read_key  # every key is read here, a union key type included (BUG-261)
  - src/confarg/exceptions.py::TypeCoercionError
effort: S
risk: medium  # the message pins sit in a few test files; nothing reads a key refusal's wording across channels
impact: behavior
severity: minor  # the refusal is loud and names the key's text, but says neither that it is a key nor which
introduced_by: [PR-5]
---

# BUG-289 — A refused dict key reads as the value

A key a dict's key type refuses is reported with the words a refused value uses, at the dict's own path, since a key has no path of its own: `dict[int, int]` handed `{"b": 1}` at `v` says `Cannot coerce str 'b' to int at 'v'`, which reads as `v` holding `'b'`.
Inside a union the line repeats the union's path too, the one variant line that still does so ([a union refusal names each variant's reason](../../architecture/types/construction.md#a-union-refusal-names-each-variants-reason)): `dict[int, int]: cannot coerce str 'b' to int at 'v'`.

Fix direction: a factory for a key refusal, called by `read_key` for a key type of one leaf and a union alike, saying it is a key, `Cannot read key 'b' of the dict at 'v' as int`, and giving a union its reason apart (`key 'b' is no int`).

Origin: latent since the initial version (PR-5), whose `_construct_dict` read each key with `_coerce_leaf(kt, k)`, the value's coercion and its refusal; BUG-261 routed every key through `read_key` and kept that refusal.

```python
from dataclasses import dataclass

import confarg


@dataclass
class T:
    v: dict[int, int] | None = None


confarg.build(T, {"v": {"b": 1}})
# expected: a refusal naming 'b' as a key of the dict at 'v'
# actual:   TypeCoercionError: Cannot coerce str 'b' to int at 'v'
```

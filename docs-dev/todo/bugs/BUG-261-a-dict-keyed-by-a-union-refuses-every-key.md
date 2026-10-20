---
filed: 2026-10-20
where:
  - src/confarg/typedload/_construct.py::_construct_dict  # each key goes through _coerce_leaf, which takes no union
  - src/confarg/_typed_merge.py  # MergeAt.key_identity reads a key by the same coercion
effort: M
needs_design: true  # how a union key type ranks a key: as a union ranks a value, or by the first branch that takes it
risk: medium  # the merge's key identity reads keys by the same coercion
impact: behavior
severity: minor  # a loud refusal; dict[Any, V] or one key type and a conversion of its own works around it
introduced_by: [PR-5]  # the initial version's _construct_dict coerces each key with _coerce_leaf
---

# BUG-261 — A dict keyed by a union refuses every key

A `dict[K, V]` whose `K` is a union (`int | None`, `int | str`) refuses every key on every channel, a Python `1` handed to `build()` included: each key is coerced by `_coerce_leaf`, a leaf coercion that takes no union, so the refusal is `Unsupported leaf type int | None`.
A union *value* is ranked by every variant ([a union ranks every value](../../architecture/design-decisions/a-union-ranks-every-value.md#a-union-ranks-every-value)); a key could be read the same way, and the merge's key identity ([which keys are one key](../../architecture/pipeline/deep-merge.md#which-keys-are-one-key)) would follow it.
Found while designing BUG-254, which reads a YAML key as its text, typed by the target.

Origin: latent since the initial version (PR-5), whose `_construct_dict` coerced each key with `_coerce_leaf`; a union key type was not in view, and the line has kept that shape since (PR-63, PR-335).

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class N:
    n: dict[int | None, int] = field(default_factory=dict)
    u: dict[int | str, int] = field(default_factory=dict)


for name, call in [
    ("argv n", lambda: confarg.load(N, argv=["--n.1", "5"], env={})),
    ("data n", lambda: confarg.build(N, {"n": {1: 5}})),
    ("argv u", lambda: confarg.load(N, argv=["--u.1", "5"], env={})),
]:
    try:
        print(name, call())
    except Exception as e:
        print(name, type(e).__name__, e)
# expected: N(n={1: 5}, u={}) twice, then N(n={}, u={1: 5})
# actual:   argv n TypeCoercionError Unsupported leaf type int | None at 'n'
#           data n TypeCoercionError Unsupported leaf type int | None at 'n'
#           argv u TypeCoercionError Unsupported leaf type int | str at 'u'
```

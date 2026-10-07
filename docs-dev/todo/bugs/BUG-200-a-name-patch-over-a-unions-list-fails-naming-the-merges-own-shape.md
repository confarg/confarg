---
filed: 2026-10-07
where:
  - src/confarg/typedload/_construct.py::_construct_union_leaf  # the closing `cannot_coerce`
effort: S
risk: low
impact: none
severity: minor  # invalid input answered with a misleading message
introduced_by: [BUG-160]  # deferred a name patch over a list as {'*': base, **patch}
---
# BUG-200 — A name patch over a union's list fails naming the merge's own `__base__` shape

On a `list[int] | dict[str, int]` field whose lower layer gave a list, a key patch (`--u.z 5`,
`APP_U__Z=5`, a later file's `u: {z: 5}`) reaches `build()` as the deferred
`{__base__: [1, 2], 'z': 5}`
([merge/build contract](../../architecture/pipeline/merge-build-contract.md#merge-build-contract)).
No variant takes that dict, and the refusal prints it, which shows the user the merge's
internal base key. A plain `list[int]` field refuses the same patch by naming the key it cannot
place. The key `*` (`--u.* 5`) fails the same way, now that it is a key like `z` (FEAT-3). Fix
direction: when the union refuses a carried `__base__`, give the list variant's own refusal, or
spell the patch without the base.

Origin: regression from the fix for BUG-160, which deferred a name patch over a list to
`build()` as `{__base__: base, **patch}` so that a namedtuple could read the name. Before it, the merge
refused the patch with `Cannot patch list 'u' with non-integer key 'z'`. Union dispatch never
learned the deferred shape. The same origin as BUG-199, a dict key `*` read as the base, which
FEAT-3 closed.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Config:
    u: list[int] | dict[str, int] = field(default_factory=list)


base = Path(tempfile.mkdtemp()) / "base.json"
base.write_text('{"u": [1, 2]}')
confarg.load(Config, argv=["--u.z", "5"], files=[str(base)], env={})

# expected: an error naming the key 'z' it cannot place in the list at 'u'
# actual:   TypeCoercionError: Cannot coerce dict {'__base__': [1, 2], 'z': 5} to list | dict at 'u'
```

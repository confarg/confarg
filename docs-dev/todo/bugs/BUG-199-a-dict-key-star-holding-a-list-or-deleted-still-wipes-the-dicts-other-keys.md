---
filed: 2026-10-07
where:
  - src/confarg/_merge.py::_merge_existing_value  # `carried is DICT_DELETE or ... isinstance(carried, list | tuple)`
  - src/confarg/_merge.py::_open_for_ops
effort: S  # once FEAT-3 gives the merge a marker no channel can type
risk: high
impact: behavior
severity: critical  # the lower layers' keys vanish with no error
blocked_by: [FEAT-3]
introduced_by: [BUG-160, BUG-116]  # BUG-160 for the list, BUG-116 for the delete
---
# BUG-199 — A dict key `*` holding a list, or deleted, still wipes the dict's other keys

BUG-185 made the merge take a `*` as a base only when it holds one: a list, or `DICT_DELETE`. A
dict's own key `*` holding a scalar now merges as any other key. When it holds a list
(`--d.* 1 2` on a `dict[str, list[int]]`) or is deleted (`--d.*-`, `APP_D__*-`), the IR spells
exactly what a base spells. The merge reads it as a base, which replaces what lay below
([deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics)), and every key the
files gave `d` is dropped. The merge alone cannot tell them apart. The fix is
[FEAT-3](../features/FEAT-3-reserved-sentinel-key-registry.md): a base marker that no channel can
type.

Origin: regression from two bug fixes. The fix for BUG-160 made a `*` override replace a dict
base, so that a stale deferred patch would not survive under it. That made the list case replace
the dict, and made the delete crash by handing `DICT_DELETE` to `build()`. The fix for BUG-116
then turned `{'*': DICT_DELETE}` into a whole-field delete's marker, which turned that crash into
silent loss. Before BUG-160, both kept `k`. BUG-185, the scalar case, came from the same origin
and is fixed.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Lists:
    d: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class Ints:
    d: dict[str, int] = field(default_factory=dict)


tmp = Path(tempfile.mkdtemp())
(tmp / "a.json").write_text('{"d": {"k": [1]}}')
(tmp / "b.json").write_text('{"d": {"k": 1, "*": 2}}')
print(confarg.load(Lists, argv=["--d.*", "1", "2"], files=[str(tmp / "a.json")], env={}))
print(confarg.load(Ints, argv=["--d.*-"], files=[str(tmp / "b.json")], env={}))

# expected: Lists(d={'k': [1], '*': [1, 2]})
#           Ints(d={'k': 1})
# actual:   Lists(d={'*': [1, 2]})
#           Ints(d={})
```

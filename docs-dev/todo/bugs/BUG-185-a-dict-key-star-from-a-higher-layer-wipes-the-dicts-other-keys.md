---
filed: 2026-10-06
where:
  - src/confarg/_merge.py::_merge_existing_value  # `if LIST_REPLACE_BASE_KEY in val: return val`
effort: S
risk: high
impact: behavior
severity: critical  # the lower layers' keys vanish with no error
introduced_by: [BUG-160]  # a '*' override replaces a dict base, read off the key alone
---
# BUG-185 — A dict key `*` from a higher layer wipes the dict's other keys

`--d.* 5` or `APP_D__*=5` on a `dict[str, int]` field sets the key `*`, and the merge reads any
override holding `*` as "a base list carried with its patch", which replaces what lay below
([deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics)). So every key the
files gave `d` is dropped, where `--d.z 5` adds beside them. Fix direction: take `*` as a base
only when it holds one — a list, or `DICT_DELETE` since BUG-116 — and merge a `*` holding
anything else as an ordinary key; the general guard is
[FEAT-3](../features/FEAT-3-reserved-sentinel-key-registry.md).

Origin: regression from the fix for BUG-160, which deferred a type-ambiguous list patch as
`{'*': base, **patch}` and, so that a stale deferred patch would not survive under it, made a
`*` override replace a dict base. It asks only whether the key is there, never whether it holds
a base, so a user's own dict key `*` replaces too. The reproduction keeps `k` at the revision
before it.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Config:
    d: dict[str, int] = field(default_factory=dict)


base = Path(tempfile.mkdtemp()) / "base.json"
base.write_text('{"d": {"k": 1}}')
print(confarg.load(Config, argv=["--d.z", "5"], files=[str(base)], env={}))
print(confarg.load(Config, argv=["--d.*", "5"], files=[str(base)], env={}))
print(confarg.load(Config, argv=[], files=[str(base)], env={"APP_D__*": "5"}, env_prefix="APP_"))

# expected: the key '*' added beside 'k', as 'z' is:
#           Config(d={'k': 1, '*': 5}) for the last two
# actual:   Config(d={'k': 1, 'z': 5})
#           Config(d={'*': 5})
#           Config(d={'*': 5})
```

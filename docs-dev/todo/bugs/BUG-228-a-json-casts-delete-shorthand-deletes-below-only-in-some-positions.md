---
filed: 2026-10-11
where:
  - src/confarg/_cast.py::fold_root_json  # the objects' own fold, `_deep_merge(base, obj)`
  - src/confarg/_merge.py::_deep_merge  # normalizes a cast's decoded value like a file's
effort: S
risk: high
impact: behavior
severity: critical  # one spelling deletes the file's value, a sibling one keeps it, both with no error
blocked_by: [Q-7]
introduced_by: [PR-87, BUG-3]  # the CLI's root --json fold, then its environment twin
---
# BUG-228 — A JSON cast's `key-` shorthand deletes below only in some positions

Every merge normalizes the dicts it meets with `_normalize_merge_ops`, a JSON cast's decoded value included, so a `"key-"` inside one becomes a delete. Whether that delete reaches the files below then depends on where it stands. Inside a field cast (`--sec.json '{"a-": null}'`) or nested in the root cast (`--json '{"sec": {"a-": null}}'`) it deletes the file's `sec.a`. At the root cast's top level (`--json '{"name-": null}'`), or nested beside a field flag that refines the same node (`--sec.b 3`), the fold's `_deep_merge` spends it on the objects and drops it, and the file's value stays. `<PREFIX>JSON` does the same through the same fold. Whichever answer Q-7 gives, the four spellings should agree. If casts do read the shorthand, the objects should fold through `_merge._merge_within_source` ([deep merge](../../architecture/pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too)), with the base's deletes kept too. If they don't, the decoded value must be kept from normalization.

Origin: latent since PR-87, which folded the root `--json` objects with `_deep_merge`, the merge between layers, so a top-level delete in them was spent there. BUG-3 copied the fold for `<PREFIX>JSON`. This is the same origin as BUG-186, which fixed the fields' half of the fold (closed), and the same shape as BUG-227. Found fixing BUG-186; reproduces on that fix's parent revision unchanged.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Sec:
    a: int = 1
    b: int = 2


@dataclass
class Config:
    name: str = "default"
    sec: Sec = field(default_factory=Sec)


base = Path(tempfile.mkdtemp()) / "base.json"
base.write_text('{"name": "file", "sec": {"a": 5}}')
for argv in (
    ["--sec.json", '{"a-": null}'],
    ["--json", '{"sec": {"a-": null}}'],
    ["--json", '{"sec": {"a-": null}}', "--sec.b", "3"],
    ["--json", '{"name-": null}'],
):
    print(confarg.load(Config, argv=argv, files=[str(base)], env={}))

# expected: the file's sec.a / name deleted every time, or kept every time (Q-7)
# actual:   Config(name='file', sec=Sec(a=1, b=2))
#           Config(name='file', sec=Sec(a=1, b=2))
#           Config(name='file', sec=Sec(a=5, b=3))
#           Config(name='file', sec=Sec(a=5, b=2))
```

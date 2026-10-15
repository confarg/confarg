---
filed: 2026-10-15
where:
  - src/confarg/_merge.py::_deep_merge
  - src/confarg/typedload/_construct.py::_construct_dict
effort: M
needs_design: true  # how the merge tells a key's identity: by spelling, or by the dict's key type
risk: high  # the merge core every channel shares
impact: behavior
severity: critical  # a delete silently deletes nothing
introduced_by: [PR-5]  # _deep_merge has matched keys by equality since the initial version
---
# BUG-244 — A string-keyed op never meets a YAML integer key

YAML reads `{1: 5}` with an integer key, while argv, the environment and JSON spell every key as a string, and `_deep_merge` matches keys by equality. So on a `dict[int, int]` loaded from YAML, a key delete, `--d.1-` or a JSON layer's `{"1": {__unset__: true}}`, meets nothing and silently deletes nothing. A value patch, `--d.1 9`, sits beside the integer key as a second key, `{1: 5, '1': 9}`, and builds right only because `_construct_dict` coerces both to `1` and the later one wins. Fix direction: decide one key identity for the merge, either the dict's key type (the merge already has its typed context, `merge_at`) or the key's spelling, and say how a YAML integer key and a string key that spell the same are combined ([deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics)). Expressions already settled the read side: a dot path falls back on the integer key ([values and references](../../architecture/expressions/values-and-references.md#spelling-a-path)).

The settled design and its build order: [fixed-length deletes and key identity](../plans/fixed-length-deletes-and-key-identity.md).

Origin: latent since the initial version (PR-5), whose `_deep_merge` matched keys by equality while YAML loaded integer keys and argv spelled strings.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Config:
    d: dict[int, int] = field(default_factory=dict)


d = Path(tempfile.mkdtemp())
(d / "base.yaml").write_text("d: {1: 5, 2: 6}\n")
(d / "del.json").write_text('{"d": {"1": {"__unset__": true}}}')
print(confarg.load(Config, files=[str(d / "base.yaml"), str(d / "del.json")], argv=[], env={}))
print(confarg.merge(Config, files=[str(d / "base.yaml")], argv=["--d.1", "9"], env={}))

# expected: Config(d={2: 6}), then one key 1 holding 9
# actual:
#   Config(d={1: 5, 2: 6})
#   {'d': {1: 5, 2: 6, '1': 9}}
```

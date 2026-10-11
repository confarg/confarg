---
filed: 2026-10-11
where:
  - src/confarg/_files.py::_include_with_siblings
  - src/confarg/_files.py::_load_includes  # the layering of several entries
effort: S
risk: medium
impact: behavior
severity: critical  # the lower file's value comes back with no error
introduced_by: [PR-5, PR-97]  # sibling keys merged over the include; then several entries layered
---
# BUG-227 — A delete beside an include never reaches the files below

A file's `name-:` deletes `name` from every file loaded before it. Written beside `__include__`, or in a later entry of an `__include__` list, it no longer does: `_include_with_siblings` and `_load_includes` merge the parts of the one document with `_deep_merge`, which spends the delete on the included content and drops it, so the earlier file's value comes back. This is the shape BUG-186 fixed for the root `json` fold, and the fix direction is the same: merge the parts of one document with `_merge._merge_within_source`, so every delete stays in the document's result and deletes in the files below it too ([deep merge](../../architecture/pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too)).

Origin: latent since the initial version (PR-5), whose `_resolve_dict` merged the sibling keys over the included dict with `_deep_merge(included, siblings)`. That is the merge between layers, so it spent the siblings' deletes there. PR-97 then layered the several entries of an `__include__` list with the same `_deep_merge`, which drops a later entry's delete the same way. The fold over the root `json` objects has the same origin pattern (BUG-186, closed, and BUG-228). Found fixing BUG-186; reproduces on that fix's parent revision unchanged.

```python
import tempfile
from dataclasses import dataclass
from pathlib import Path

import confarg


@dataclass
class Config:
    name: str = "default"


d = Path(tempfile.mkdtemp())
(d / "base.json").write_text('{"name": "file"}')
(d / "inc.json").write_text('{"name": "inc"}')
(d / "del.json").write_text('{"name-": null}')
(d / "flat.json").write_text('{"name": "inc", "name-": null}')
(d / "siblings.json").write_text('{"__include__": "inc.json", "name-": null}')
(d / "entries.json").write_text('{"__include__": ["inc.json", "del.json"]}')
for top in ("flat.json", "siblings.json", "entries.json"):
    print(confarg.load(Config, argv=[], files=[str(d / "base.json"), str(d / top)], env={}))

# expected: Config(name='default') three times
# actual:   Config(name='default')
#           Config(name='file')
#           Config(name='file')
```

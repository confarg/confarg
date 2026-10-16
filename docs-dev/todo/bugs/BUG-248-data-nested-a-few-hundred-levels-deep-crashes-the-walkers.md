---
filed: 2026-10-16
where:
  - src/confarg/_files.py::_resolve_node
  - src/confarg/typedload/_construct.py::construct
effort: L
needs_design: true  # the depth bound for data, on every channel that carries JSON or a file
risk: high
impact: behavior
severity: major  # a raw RecursionError for data a JSON parser accepts; minor once a bound makes it invalid input
introduced_by: [PR-5]  # the initial merge and construction walk the data recursively
---
# BUG-248 — Data nested a few hundred levels deep crashes the walkers

`json.loads` reads a document nested a few hundred levels deep, but confarg's walkers over the data recurse in Python, so `load()` fails with a raw `RecursionError`: from construction (`construct` → `_construct_any`) at about 300 levels, and from file loading (`_files._resolve_node`) at about 500, in `merge()` too. A 300-level document is about 1.5 kB. BUG-145 bounds the depth of an expression body; this is the same failure for the data itself, on every walker (loading, merge, the default layer, construction, dump) and every channel that carries nested data (files, env and argv JSON). Fix direction: bound the depth where the data enters and refuse deeper data with a confarg error, the bound being the decision to record. Precedents: `serde_json` caps recursion at 128, and BUG-145's expression bound is 100.

Origin: latent since the initial version (PR-5), whose `_deep_merge` and construction walk the data recursively with no depth bound.

```python
import json
import pathlib
import tempfile
from dataclasses import dataclass
from typing import Any

import confarg


@dataclass
class Config:
    d: Any = None


nested: dict = {}
for _ in range(300):
    nested = {"a": nested}
path = pathlib.Path(tempfile.mkdtemp(), "config.json")
path.write_text(json.dumps({"d": nested}))
try:
    confarg.load(Config, argv=[], env={}, files=[path])
except Exception as exc:
    print(type(exc).__name__, exc)
# expected: a ConfargError naming the file and the depth, or the config built
# actual:   RecursionError maximum recursion depth exceeded
```

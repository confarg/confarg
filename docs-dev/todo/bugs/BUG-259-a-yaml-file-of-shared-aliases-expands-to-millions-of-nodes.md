---
filed: 2026-10-19
where:
  - src/confarg/_files.py::_resolve_node  # rebuilds each node at each position it is reached by
  - src/confarg/_files.py::_load_yaml_item
effort: L
needs_design: true  # the bound: aliases counted (yaml.v3), nodes counted once expanded, or a size per format
risk: high
impact: behavior  # a bound refuses only a document no configuration is written as
severity: critical  # a configuration can exhaust the host: 400 bytes load for minutes
introduced_by: [PR-5]  # inferred from code reading: PR-5 cannot type the reproduction, so it was not run there
---

# BUG-259 — A YAML file of shared aliases expands to millions of nodes

A YAML anchor can be aliased many times, and an anchored node can alias the one before it, so a file of a few hundred bytes names a tree of millions of nodes (the "billion laughs" shape).
PyYAML builds it cheaply, sharing each node, but confarg's walkers rebuild a node at every position it is reached by: 10⁶ leaves from 349 bytes take 14 seconds to load, each further line ten times more, and the memory with it.
The depth bound does not catch it, since the tree is only as deep as its lines ([a configuration nests at most 64 levels](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#a-configuration-nests-at-most-64-levels)); the depth count itself walks a shared node once.
Fix direction: refuse such a document where it is loaded, which needs a bound to decide: Go's yaml.v3 refuses "excessive aliasing" by the ratio of alias expansions to the document's size (Kubernetes' CVE-2019-11253), and a count of the nodes the expanded document holds would bound JSON and TOML too.

Origin: latent since the initial version (PR-5) *(inferred)*: its walkers copy the data position by position, which expands a shared node; PR-5 refuses the reproduction's `Any` and `dict[str, Any]` fields, so the timing could not be bisected there.

```python
import pathlib
import tempfile
import time
from dataclasses import dataclass
from typing import Any

import confarg


@dataclass
class Config:
    d: Any = None


tmp = pathlib.Path(tempfile.mkdtemp())
for levels in (4, 5, 6):
    lines = ["d:", "  l0: &l0 [x, x, x, x, x, x, x, x, x, x]"]
    for i in range(1, levels):
        lines.append(f"  l{i}: &l{i} [" + ", ".join([f"*l{i - 1}"] * 10) + "]")
    text = "\n".join(lines) + "\n"
    (tmp / "b.yaml").write_text(text)
    start = time.perf_counter()
    confarg.load(Config, argv=[], env={}, files=[tmp / "b.yaml"])
    print(f"{len(text)} bytes, 10^{levels} leaves: {time.perf_counter() - start:.2f}s")
# expected: a confarg error refusing the document, or a load in milliseconds
# actual:   227 bytes, 10^4 leaves: 0.23s
#           288 bytes, 10^5 leaves: 1.39s
#           349 bytes, 10^6 leaves: 14.04s
```

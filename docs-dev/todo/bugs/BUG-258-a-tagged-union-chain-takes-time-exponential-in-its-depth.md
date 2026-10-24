---
filed: 2026-10-19
where:
  - src/confarg/_api.py::_strip_locals_node  # profiled: asks _locals_keys_at at every node
  - src/confarg/_parse_cli.py::_locals_keys_at  # re-walks the type from the root, unnamed, so a union forks at every level
  - src/confarg/_pipeline.py::_iter_namespace_nodes  # asks it per node too (inferred: not profiled)
  - src/confarg/_pipeline.py::_LayerReading  # asks it per node too (inferred: not profiled)
effort: M
risk: high
impact: behavior
severity: critical  # a configuration can exhaust the host: a 30-level tagged chain runs for hours
introduced_by: [PR-105]  # feat: Scratch variable space and global variable paths, which wrote _strip_locals_node
---

# BUG-258 — A tagged union chain takes time exponential in its depth

Building a recursive struct through a union of its variants (`child: A | B | None`, each level naming its class) takes about twice as long per level: 15 levels take a second and a half, 20 levels 45 seconds, a 30-level configuration hours, well inside the 64 levels a configuration may nest ([a configuration nests at most 64 levels](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#a-configuration-nests-at-most-64-levels)).
`_api._strip_locals_node` asks `_parse_cli._locals_keys_at(target, path)` at every node, and that resolves the path from the root through `_walk_path` with no naming, so the walk forks into both variants at each union and visits 2^depth branches per node.
Fix direction: carry the type down the strip's own walk, reading the class each node names, rather than re-walking from the root per node; the pipeline's other per-node callers of `_locals_keys_at` likely need the same *(inferred)*.
See [locals](../../architecture/locals.md#per-node-namespaces) and [one walk, many questions](../../architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions).

Origin: a regression from PR-105, which added the per-node namespaces and stripped them after resolution, asking at each node which keys address one there.
The revision before it builds 14 levels in 3 ms; PR-105 in 8.5 s; REF-43, which moved the walk into `_walk_path`, left it as it was (1.8 s before it and after it).

```python
import time
from dataclasses import dataclass

import confarg


@dataclass
class A:
    child: "A | B | None" = None


@dataclass
class B:
    child: "A | B | None" = None
    x: int = 0


def chain(n):
    node = {"class": "__main__.B"}
    for _ in range(n):
        node = {"child": node, "class": "__main__.B"}
    return {"child": node}


for n in (5, 10, 15, 20):
    start = time.perf_counter()
    confarg.from_dict(A, chain(n))
    print(n, f"{time.perf_counter() - start:.3f}s")
# expected: each depth in about the same few milliseconds, as before PR-105
# actual:   5 0.003s
#           10 0.046s
#           15 1.386s
#           20 44.734s
```

---
filed: 2026-10-19
where:
  - src/confarg/_parse_cli.py::_walk_path  # lists every branch with its history: 2^depth below a union met at each level
  - src/confarg/_parse_cli.py::_check_mount_subpath  # walks without naming
  - src/confarg/_tags.py::_argv_tag_names_member  # walks without the naming argv gives
  - src/confarg/_parse_env.py::_env_spelling  # its `reached` walks without naming
  - src/confarg/cli/_build.py  # registration walks without naming
effort: L
needs_design: true  # the predicates read each branch's history: a branch DAG, or predicates folded per state
risk: high
impact: behavior  # the answers stay; a parse that ran for hours ends
severity: critical  # a flag or variable can exhaust the host; a close call with major: argv and the environment are the operator's own
introduced_by: [PR-5]  # the initial _resolve_field_type recursed into each union variant over the rest of the path
---

# BUG-260 — A deep flag or variable below a recursive union takes exponential time

A flag or an environment variable whose path runs through a union at every level (`child: A | B | None`, recursively) takes about twice as long per level to parse: 14 levels take a second on argv and five in the environment, a 30-level path hours.
`_parse_cli._walk_path` lists every branch the walk can take with the stones it stood on, and a union met at each level doubles them; the questions about a path (`_is_dict_at_path`, `_is_collection_patch_path`, `_sequence_refusal`, …) read those histories.
Naming every level on argv does not help, since several callers walk without the naming the data gives (`_tags._argv_tag_names_member`, `_parse_env._env_spelling`'s `reached`, the adapters' registration).
Fix direction: walk a DAG of states, which `_step` and `_step_states` already make (BUG-258), and fold each predicate over it, or pass the naming where it is known, which leaves a path nothing names exponential *(inferred)*.
See [one walk, many questions](../../architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions).

Origin: latent since the initial version (PR-5): its `_resolve_field_type` recursed into each union variant over the remaining path, and every walk since kept the per-variant fork.
BUG-258 removed the same fork from the walkers over data, which carry deduplicated states; a configuration file reaches only those.

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


for n in (10, 12, 14):
    path = "child." * n + "x"
    named = [a for k in range(1, n + 1) for a in (f"--{'child.' * k}class", "__main__.B")]
    for label, kw in [
        ("argv", {"argv": [f"--{path}", "1"], "env": {}}),
        ("argv named", {"argv": [*named, f"--{path}", "1"], "env": {}}),
        ("env", {"argv": [], "env": {"P_" + path.upper().replace(".", "__"): "1"}, "env_prefix": "P_"}),
    ]:
        start = time.perf_counter()
        confarg.merge(A, **kw)
        print(n, label, f"{time.perf_counter() - start:.3f}s")
# expected: each depth in a few milliseconds
# actual:   10 argv 0.061s
#           10 argv named 0.078s
#           10 env 0.306s
#           12 argv 0.233s
#           12 argv named 0.248s
#           12 env 1.222s
#           14 argv 0.921s
#           14 argv named 0.855s
#           14 env 4.846s
```

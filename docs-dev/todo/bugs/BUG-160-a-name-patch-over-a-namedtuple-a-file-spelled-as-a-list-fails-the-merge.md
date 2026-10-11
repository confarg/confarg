---
filed: 2026-10-05
where:
  - src/confarg/_merge.py::_apply_list_ops
  - src/confarg/_parse_cli.py::_promote_namedtuple_positional
effort: M
risk: high
impact: behavior
needs_design: true
---
# BUG-160 — A name patch over a namedtuple a file spelled as a list fails the merge

Within the CLI, `--pt 1 2 --pt.x 9` builds `Pt(x=9, y=2)`: the loop knows the field is a
namedtuple, and `_promote_namedtuple_positional` re-keys the positional list by field name
before the name key lands. Across channels nothing does, so a file's `pt: [1, 2]` under
`--pt.x 9`, or under `APP_PT__X=9`, reaches the untyped merge as a list patched by a
non-integer key, and `_apply_list_ops` refuses it. That breaks
[cross-channel parity](../../architecture/invariants.md#cross-channel-parity). The merge
cannot ask the type
([merge stays unvalidated](../../architecture/invariants.md#merge-stays-unvalidated)), so the
fix needs a design pass. One way is to defer the reconciliation to `build()`, which
[Q-1](../questions/Q-1-should-a-mixed-name-index-spelling-of-a-namedtuple-build.md) asks
about for a mixed dict. See
[a namedtuple is a fixed-length sequence](../../architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence).

```python
import os
import tempfile
from dataclasses import dataclass
from typing import NamedTuple

import confarg


class Pt(NamedTuple):
    x: int
    y: int


@dataclass
class Cfg:
    pt: Pt


path = os.path.join(tempfile.mkdtemp(), "base.yaml")
with open(path, "w") as f:
    f.write("pt: [1, 2]\n")

print("cli only:", confarg.load(Cfg, argv=["--pt", "1", "2", "--pt.x", "9"], env={}))
try:
    print("file+cli:", confarg.load(Cfg, argv=["--config", path, "--pt.x", "9"], env={}))
except Exception as e:
    print("file+cli:", type(e).__name__, e)
try:
    print("file+env:", confarg.load(Cfg, argv=["--config", path], env={"APP_PT__X": "9"}, env_prefix="APP_"))
except Exception as e:
    print("file+env:", type(e).__name__, e)

# expected: Cfg(pt=Pt(x=9, y=2)) three times
# actual:
#   cli only: Cfg(pt=Pt(x=9, y=2))
#   file+cli: ConfargError Cannot patch list 'pt' with non-integer key 'x'. List patches must use integer string keys (e.g. {'0': ..., '1': ...}).
#   file+env: ConfargError Cannot patch list 'pt' with non-integer key 'x'. List patches must use integer string keys (e.g. {'0': ..., '1': ...}).
```

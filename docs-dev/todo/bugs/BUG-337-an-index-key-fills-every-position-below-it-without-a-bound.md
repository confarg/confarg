---
filed: 2026-11-12
where:
  - src/confarg/typedload/_construct.py::_build_items
effort: M
risk: medium
impact: behavior  # a bound refuses an index that builds today
severity: critical  # a configuration can exhaust the host: 20 bytes name 10^6 elements, on argv, in the environment and in a file
needs_design: true  # the bound, and whether the copy budget's 100 000 is it
introduced_by: [PR-5]  # latent: the index-keyed form, with its range(max_idx + 1) fill, is in the oldest revision probed
---

# BUG-337 — An index key fills every position below it, without a bound

A list whose element type takes `None` builds from an index-keyed dict by filling every index from 0 to the highest key: `_build_items` takes `max(positions)` and constructs `range(max_idx + 1)` elements, an absent one as `None`.
So a single key names as many elements as its number says, on every channel: `--xs.1000000 5`, `APP_XS__1000000=5` and a file's `xs: {"1000000": 1}` each build a list of 1 000 001 elements, at about 55 µs an element.
[A configuration copies at most 100 000 positions](../../architecture/design-decisions/a-configuration-copies-at-most-100000-positions.md#a-configuration-copies-at-most-100-000-positions) counts what a document copies and never what an author wrote, and an index fill is neither: the one key is one position in the data, and no note bounds the elements it makes or accepts them ([limitations](../../architecture/limitations.md) only says a gap needs an Optional element).
Fix direction, the maintainer's to settle: refuse an index-keyed form whose fill exceeds a bound, reusing the copy budget's 100 000 or a bound of its own, with a confarg error naming the index; or build no fill at all for a gap-free form only.
An element type that takes no `None` refuses the gap, but only after listing it: `build(L, {"x": {"10000000": 1}})` on `list[int]` takes 1.8 s and raises a `TypeCoercionError` whose message is 89 MB, every missing index spelled out, and a key of 10^9 would exhaust memory before it raised.

Origin: latent since PR-5, which already read `max(int(k) for k in data)` and filled `range(max_idx + 1)`; no revision since bounded it, and the position budget (BUG-259) was written for copies.

```python
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

import confarg


@dataclass
class Cfg:
    xs: list[Optional[int]]


N = 100_000
path = os.path.join(tempfile.mkdtemp(), "c.yaml")
with open(path, "w") as f:
    f.write(f'xs:\n  "{N}": 1\n')
for name, kw in [
    ("argv", dict(argv=[f"--xs.{N}", "5"], env={})),
    ("env", dict(argv=[], env={f"APP_XS__{N}": "5"}, env_prefix="APP_")),
    ("file", dict(argv=[], env={}, files=[path])),
]:
    t = time.time()
    print(name, len(confarg.load(Cfg, **kw).xs), f"{time.time() - t:.1f}s")
# expected: a refusal naming the index, or at most the keys given
# actual (10^6 instead of 10^5 takes about 55 s, 10^9 exhausts memory):
# argv 100001 5.5s
# env 100001 5.6s
# file 100001 5.5s
```

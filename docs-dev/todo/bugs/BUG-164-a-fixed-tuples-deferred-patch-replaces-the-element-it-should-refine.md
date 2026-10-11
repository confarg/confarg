---
filed: 2026-10-05
where:
  - src/confarg/typedload/_construct.py::_construct_tuple
effort: S
risk: high
impact: behavior
---
# BUG-164 — A fixed tuple's deferred patch replaces the element it should refine

When a patch over a base list holds an index past the base's end, the merge defers the whole
patch to `build()` as `{'*': base, ...}`
([merge/build contract](../../architecture/pipeline/merge-build-contract.md#merge-build-contract)).
`_construct_tuple` then reads each in-range key as a replacement (`pos.get(i, base_seq[i])`),
where the merge itself, had nothing escaped, would have refined that element through
`_merge._merge_existing_value`
([deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics)). So `--t.0.a 9` refines a
file's `[[1, 2]]` alone but replaces it as soon as `--t.1 5` rides beside it. A namedtuple's
deferred patch already refines (`_lay_patch_over_positions`, BUG-160), so the two fixed-length
sequences disagree. Fix direction: lay each position through `_merge_existing_value`, as the
namedtuple does.

```python
import os
import tempfile
from dataclasses import dataclass
from typing import NamedTuple

import confarg


class In(NamedTuple):
    a: int
    b: int


@dataclass
class Cfg:
    t: tuple[In, int] = (In(0, 0), 0)


path = os.path.join(tempfile.mkdtemp(), "base.yaml")
with open(path, "w") as f:
    f.write("t: [[1, 2]]\n")

for argv in (["--t.0.a", "9", "--t.1", "5"], ["--t.1", "5", "--t.0.a", "9"]):
    try:
        print(argv, "->", confarg.load(Cfg, argv=["--config", path, *argv], env={}).t)
    except Exception as e:
        print(argv, "->", type(e).__name__, e)

# expected: (In(a=9, b=2), 5) twice -- the .0.a patch refines the file's [1, 2]
# actual:
#   ['--t.0.a', '9', '--t.1', '5'] -> MissingFieldError Missing required field 't[0].b' of type <class 'int'>. Set it via CLI (--t[0].b), environment variable, or config file.
#   ['--t.1', '5', '--t.0.a', '9'] -> MissingFieldError Missing required field 't[0].b' of type <class 'int'>. Set it via CLI (--t[0].b), environment variable, or config file.
```

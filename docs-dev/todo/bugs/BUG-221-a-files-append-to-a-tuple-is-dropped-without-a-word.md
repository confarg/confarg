---
filed: 2026-10-10
where:
  - src/confarg/typedload/_construct.py::_indexed_dict_to_positions
  - src/confarg/typedload/_construct.py::_resolve_tuple_partial
effort: S
risk: medium
impact: config
severity: critical  # the file loads, and the tuple keeps its default as if the key were absent
introduced_by: [PR-5]  # the tuple patch skipped any key it read no index in
---
# BUG-221 — A file's append to a tuple is dropped without a word

The command line refuses `--t+ 1` on a tuple field ("not a list, set, or frozenset"). A file's `t+: [1]`, or its `t: {__append__: [1]}`, reaches `build()` as `{ListOp.APPEND: [1]}` instead, and a tuple with a default is patched in place by `_resolve_tuple_partial`, which reads the keys through `_indexed_dict_to_positions` with `tolerate_non_int=True`: the marker is no integer, so it is skipped as a stray segment, and the tuple keeps its default. It holds for a fixed tuple and a variadic `tuple[int, ...]` alike. The plain string `"__append__"` is refused there (BUG-209); the marker, the one a channel produces, is not. A dict field refuses the marker in `_construct_dict` (`list_op_on_a_dict`), which is the behavior to match ([deep merge](../../architecture/pipeline/deep-merge.md#no-channel-types-an-op)).

Fix direction: `_indexed_dict_to_positions`, the one index reader, refuses a `ListOp` key whether or not it tolerates stray segments, with the message the dict field gives.

Origin: latent since the initial version (PR-5): the file's `key+:` shorthand stored an append op that the tuple patch skipped as a key it read no index in, while the CLI refused the append on a tuple. FEAT-3 kept the skip when it made the op a marker. It reproduces unchanged at PR-5 with `args=` for `argv=`.

```python
import pathlib
import tempfile
from dataclasses import dataclass

import confarg


@dataclass
class Cfg:
    t: tuple[int, int] = (0, 0)


f = pathlib.Path(tempfile.mkdtemp()) / "c.yaml"
f.write_text("t+: [1]\n")
try:
    print(confarg.load(Cfg, files=[str(f)], argv=[], env={}))
except Exception as e:
    print(type(e).__name__, e)

# expected: a TypeCoercionError refusing the append at 't', as --t+ 1 is refused
# actual:   Cfg(t=(0, 0))
```

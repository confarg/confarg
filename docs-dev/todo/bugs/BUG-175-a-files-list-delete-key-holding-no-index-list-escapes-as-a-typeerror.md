---
filed: 2026-10-05
where:
  - src/confarg/_merge.py::_apply_list_ops
effort: S
risk: low
impact: none
severity: minor  # only a file writing a reserved key meets it
introduced_by: [PR-5, PR-9]  # the '-' reader, then the '~' reader written the same way beside it
---
# BUG-175 — A file's list-delete key holding no index list escapes as a raw TypeError

The merge reads the indices under `'-'` and `'~'` by iterating them, so a configuration file
that writes either key itself with a scalar — `xs: {"-": 0}` — escapes as a raw `TypeError`
rather than a `ConfargError` naming the field. No channel's parser writes these keys from what
the user typed (BUG-170), so only a file reaches it. `'*'` has had one reader that refuses a
value holding no list since BUG-170 (`_merge._replace_base`); the two delete keys want the same,
or the general guard [FEAT-3](../features/FEAT-3-reserved-sentinel-key-registry.md) proposes.
See [deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics).

Origin: latent since the initial version (PR-5), whose merge iterated the `'-'` key's value as
indices without checking that it holds a list; PR-9 added `'~'` with the same read. BUG-170's fix
gave `'*'` a guard and stopped every channel's parser from writing these keys from what the user
typed, which left a file as the only way in.

```python
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Cfg:
    xs: list[int] = field(default_factory=list)


d = Path(tempfile.mkdtemp())
(d / "base.json").write_text(json.dumps({"xs": [1, 2]}))
for doc in ({"xs": {"-": 0}}, {"xs": {"+": [3], "~": 0}}):
    (d / "patch.json").write_text(json.dumps(doc))
    try:
        print(doc, "->", confarg.load(Cfg, argv=[], env={}, files=[str(d / "base.json"), str(d / "patch.json")]))
    except Exception as e:
        print(doc, "->", type(e).__name__, e)

# expected: a ConfargError naming 'xs' and the key holding no list of indices
# actual:
#   {'xs': {'-': 0}} -> TypeError 'int' object is not iterable
#   {'xs': {'+': [3], '~': 0}} -> TypeError 'int' object is not iterable
```

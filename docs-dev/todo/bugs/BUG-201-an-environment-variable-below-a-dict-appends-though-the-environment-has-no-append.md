---
filed: 2026-10-07
where:
  - src/confarg/_merge.py::_normalize_merge_ops  # reads the file shorthand on every layer, the environment's included
  - src/confarg/_parse_env.py::_parse_env
effort: S  # once FEAT-18 settles whether the environment appends
risk: medium
impact: config  # one of the two spellings changes meaning, whichever way FEAT-18 goes
severity: minor  # the top-level variable is warned about; the nested one does what the flag does
blocked_by: [FEAT-18]
introduced_by: [PR-5]  # _deep_merge normalizes the `key+` shorthand of every layer it merges
---
# BUG-201 — An environment variable below a dict appends, though the environment has no append

The environment has no append spelling
([FEAT-18](../features/FEAT-18-no-append-spelling-in-the-environment.md),
[limitations](../../architecture/limitations.md#collections)): `APP_XS+=3` is warned about as
naming no field and dropped. One level down it appends. `APP_D__K+=3` on a
`dict[str, list[int]]` reaches the merge as the key `k+`, and `_merge._normalize_merge_ops`, which
reads a file's `key+:` shorthand, runs on every layer `_deep_merge` merges, so it reads the
variable's key as an append too. The environment parser never decides it, and the walk never
types it: the same suffix is an unknown field at the root and an append below a dict. Fix
direction: whichever way FEAT-18 settles, one decision in the environment's own parse, and a
normalization that reads only a file's keys
([deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics)).

Origin: latent since the initial version (PR-5), whose `_deep_merge` normalized the shorthand of
both its arguments, whatever channel they came from, while its environment parser warned about a
first segment naming no field. It reproduces unchanged at PR-28, the oldest revision the
reproduction runs on.

```python
import json
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class C:
    d: dict[str, list[int]] = field(default_factory=dict)
    xs: list[int] = field(default_factory=list)


base = Path(tempfile.mkdtemp()) / "b.json"
base.write_text(json.dumps({"d": {"k": [1]}, "xs": [1]}))
for env in ({"APP_D__K+": "3"}, {"APP_XS+": "3"}):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cfg = confarg.load(C, argv=[], env=env, env_prefix="APP_", files=[str(base)])
    print(env, "->", cfg, [str(x.message)[:44] for x in w])

# expected: the two variables read alike, both appending or both refused
# actual:
#   {'APP_D__K+': '3'} -> C(d={'k': [1, 3]}, xs=[1]) []
#   {'APP_XS+': '3'} -> C(d={'k': [1]}, xs=[1]) ["Environment variable 'APP_XS+' has no matchi"]
```

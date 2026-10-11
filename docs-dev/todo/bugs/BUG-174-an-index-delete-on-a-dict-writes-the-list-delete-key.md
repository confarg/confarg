---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_parse_flag_mode
  - src/confarg/_parse_cli.py::_handle_delete_token
  - src/confarg/_parse_env.py::_handle_env_delete
effort: S
risk: medium
impact: behavior
---
# BUG-174 — An index delete on a dict writes the list-delete key into the dict

Both channels decide "is this delete a list-index delete?" with `int()` on the last segment
alone, never asking the type. On a dict the key `1` is a key like `a`, but `--d.1-` and
`APP_D__1-` record a list delete, `{'-': [1]}`, beside the dict's keys, and `build()` then
fails on a field named `-`. `--d.a-` deletes its key as it should. Fix direction: a delete is
a list-index delete only where the walk stands on a sequence, the rest are key deletes; this
is the one decoder [REF-84](../refactors/REF-84-env-delete-suffix-decoded-twice.md) asks for,
and the merge vocabulary it protects is in
[deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics).

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Cfg:
    d: dict[str, int] = field(default_factory=dict)


base = Path(tempfile.mkdtemp()) / "base.json"
base.write_text('{"d": {"1": 5, "a": 6}}')
for argv, env in ((["--d.1-"], {}), ([], {"APP_D__1-": "x"}), (["--d.a-"], {})):
    kw = {"argv": argv, "env": env, "env_prefix": "APP_", "files": [str(base)]}
    print(argv or env, "->", confarg.merge(Cfg, **kw))
    try:
        print("   ", confarg.load(Cfg, **kw))
    except Exception as e:
        print("   ", type(e).__name__, e)

# expected: the first two delete the key '1' as the third deletes 'a': {'d': {'a': 6}}
# actual:
#   ['--d.1-'] -> {'d': {'1': 5, 'a': 6, '-': [1]}}
#       TypeCoercionError Cannot coerce list [1] to int at 'd.-'
#   {'APP_D__1-': 'x'} -> {'d': {'1': 5, 'a': 6, '-': [1]}}
#       TypeCoercionError Cannot coerce list [1] to int at 'd.-'
#   ['--d.a-'] -> {'d': {'1': 5}}
#       Cfg(d={'1': 5})
```

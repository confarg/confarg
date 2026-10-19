---
filed: 2026-10-14
where:
  - src/confarg/_api.py::dump
  - src/confarg/_serialize.py::_serialize
effort: S
risk: low
impact: behavior
severity: minor  # the reload fails loudly; the key can be given no other way
introduced_by: [PR-5, FEAT-3]  # PR-5's dump wrote dict keys untouched while its files read __include__; FEAT-3 reserved the four op keys
---
# BUG-241 — A dict key named like a reserved key dumps as the key a file reads

`dump()` writes a dict field's keys as they stand, so a `dict[str, int]` built in Python with the key `__append__` or `__include__` is dumped as that key, and `dump_file` writes it to a file, which reads it as the op or the include rather than as data ([reserved keys](../../architecture/config-files/reserved-keys.md#reserved-file-only-keys)). The reload fails, or, with a value of the right shape, means something else. Fix direction: `dump()` refuses a data key in `_defaults.RESERVED_KEYS`, at any depth, naming its path, as argv and the environment refuse one; `dump_file` of an instance goes through `dump()`, and a raw dict passed to `dump_file` is a document, whose keys are written as a file spells them.

Origin: latent since the initial version (PR-5), whose `dump()` wrote a dict's keys untouched while its files read `__include__` as their own (`_files.INCLUDE_KEY`); FEAT-3 (PR-352) widened it to the four op keys it reserved.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Cfg:
    d: dict[str, int] = field(default_factory=dict)


saved = Path(tempfile.mkdtemp()) / "out.yaml"
for key in ("__append__", "__include__"):
    cfg = Cfg(d={key: 1})
    try:
        print(key, "dump ->", confarg.dump(cfg))
        confarg.dump_file(cfg, saved)
        print("   reload ->", confarg.load(Cfg, files=[str(saved)], argv=[], env={}))
    except Exception as e:
        print("   ", type(e).__name__, e)

# expected: dump() refuses the key, naming d.__append__ (then d.__include__)
# actual:
#   __append__ dump -> {'d': {'__append__': 1}}
#       TypeCoercionError Cannot apply '__append__' to the dict at 'd': it is an operation on a list.
#   __include__ dump -> {'d': {'__include__': 1}}
#       ConfargError __include__ must be a path string or a dict with a string 'path' key, got 1
```

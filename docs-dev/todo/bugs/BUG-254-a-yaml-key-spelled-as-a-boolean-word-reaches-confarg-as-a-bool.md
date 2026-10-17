---
filed: 2026-10-18
where:
  - src/confarg/_files.py::_load_yaml_item
effort: M
needs_design: true  # read keys as YAML 1.2 does (a resolver of our own), or name the quirk in the refusal
risk: medium  # a dict[bool, ...] field reads its keys through the same loader
impact: behavior
severity: minor  # quoting the key works; the refusal names a field nobody wrote
introduced_by: [PR-5]  # the initial version's loader, yaml.safe_load
---

# BUG-254 — A YAML key spelled as a boolean word reaches confarg as a bool

PyYAML's `safe_load` reads YAML 1.1, where a bare `off`, `on`, `yes`, `no`, `y` or `n` is a boolean, keys included.
So a field named `off` cannot be set by an unquoted YAML key: `off: 5` reaches confarg as the key `False`, and the refusal names a field nobody wrote (`Unknown field(s) ['False']`).
Quoting the key (`'off': 5`) works, as do the TOML and JSON spellings.
[BUG-249](BUG-249-the-yaml-formatter-strips-quotes-the-loader-needs.md) is the same YAML 1.1 reading of a value, met by the repository's formatter; [the token model](../../architecture/types/token-model.md#token-model) keeps a file's value as the file typed it, which is why a value's `yes` is no problem for a `str` field, but a key's type decides which field it names.
Fix direction: read a mapping's keys as YAML 1.2 reads them (a loader whose resolver leaves the boolean words as strings in key position), or keep the reading and name the quirk in the refusal, as the time and duration refusals name YAML's base-60 numbers.
Found while writing the timezone tests of FEAT-51.

Origin: latent since the initial version (PR-5), whose YAML loader is `yaml.safe_load` with its YAML 1.1 resolver; the loaders have been reorganized since (REF-19, PR-208) without changing it.

```python
import pathlib
import tempfile
from dataclasses import dataclass

import confarg


@dataclass
class Switches:
    off: int = 0
    on: int = 0


path = pathlib.Path(tempfile.mkdtemp(), "c.yaml")
path.write_text("off: 5\n")
try:
    print(confarg.load(Switches, argv=[], env={}, files=[path]))
except Exception as e:
    print(type(e).__name__, e)
# expected: Switches(off=5, on=0)
# actual:   TypeCoercionError Unknown field(s) ['False'] for Switches at ''. Valid fields: ['off', 'on']
```

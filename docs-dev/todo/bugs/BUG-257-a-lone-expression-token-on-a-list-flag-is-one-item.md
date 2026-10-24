---
filed: 2026-10-18
where:
  - src/confarg/_parse_cli.py::_varlen_value
  - src/confarg/_parse_cli.py::_lone_json_array
  - src/confarg/cli/_build.py
effort: M  # vanilla's loop and the adapters' registration of the flag, on five front-ends
risk: medium
impact: behavior
severity: minor  # a loud TypeCoercionError; `--names.json '"${other}"'` spells the whole list
introduced_by: [PR-5]  # the CLI read every token of a list flag as an item, the environment the whole variable as the value
---

# BUG-257 — A lone expression token on a list flag is one item, where the environment reads it as the whole list

`APP_NAMES='${other}'` sets a `list[str]` field to the list `${other}` resolves to, and so does `--names.json '"${other}"'`, but `--names '${other}'` stores `['${other}']`, a list of one item, which construction then refuses as a list where a `str` item stands.
A lone `[`-led token is already a whole-value spelling of such a flag (`_lone_json_array`, [token consumption](../../architecture/cli-parsing/token-consumption.md#token-consumption)); a lone `${...}` token is not.
Fix direction: decide whether a lone token that is one whole expression stands for the whole value, as the `[` token does, on vanilla's loop and the adapters' registration alike; `--names a '${other}'` would stay two items.

Origin: latent since the initial version (PR-5), whose CLI made every token of a list flag an item and whose environment parser stored a variable's text as the whole value; the reproduction gives the same two results at PR-5.

```python
import pathlib
import tempfile
from dataclasses import dataclass, field

import confarg


@dataclass
class Cfg:
    names: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)


o = pathlib.Path(tempfile.mkdtemp()) / "o.yaml"
o.write_text("other: [x, y]\n")
for label, kw in (
    ("argv", {"argv": ["--names", "${other}"], "env": {}}),
    ("env ", {"argv": [], "env": {"APP_NAMES": "${other}"}, "env_prefix": "APP_"}),
):
    try:
        print(label, confarg.load(Cfg, files=[o], **kw).names)
    except Exception as e:
        print(label, type(e).__name__, e)

# expected: both ['x', 'y']
# actual:
#   argv TypeCoercionError Cannot coerce list ['x', 'y'] to str at 'names[0]'
#   env  ['x', 'y']
```

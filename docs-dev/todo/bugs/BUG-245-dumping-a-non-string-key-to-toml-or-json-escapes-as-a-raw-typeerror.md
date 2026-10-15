---
filed: 2026-10-15
where:
  - src/confarg/_files.py::_dump_toml
  - src/confarg/_files.py::_dump_json
  - src/confarg/_api.py::dump_file
effort: S
needs_design: true  # write the key as JSON's spelling, or refuse it naming the key and the formats that hold it
risk: low
impact: behavior
severity: minor  # loud, though a raw TypeError; dumping to YAML is the workaround
introduced_by: [PR-5]  # the initial version wrote TOML with tomli_w and loaded YAML's non-string keys as they are
---
# BUG-245 — Dumping a non-string key to TOML or JSON escapes as a raw `TypeError`

A YAML file loads `d: {1: 5}` with an integer key and `a: {2020-01-01: 6}` with a date key, and `merge()` keeps both as written. `dump_file` hands them to the format's writer as they are: `tomli_w` refuses every key that is no string, and `json` refuses a date, each with a raw `TypeError` rather than a confarg error naming the key. A YAML dump writes both. Fix direction, to decide first: write a non-string key as JSON's spelling of it, the string the other channels already meet it by ([which keys are one key](../../architecture/pipeline/deep-merge.md#which-keys-are-one-key)), so `1` reads back as `"1"` and a typed field coerces it again; or refuse it with a `ConfargError` naming the key's path and the format that can hold it. JSON already writes `1` as `"1"` itself.

Origin: latent since the initial version (PR-5), whose `dump_file` wrote TOML through `tomli_w` while YAML loaded non-string keys as they are. Found while settling BUG-244's key identity.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import confarg


@dataclass
class Config:
    d: dict[int, int] = field(default_factory=dict)
    a: Any = None


tmp = Path(tempfile.mkdtemp())
(tmp / "base.yaml").write_text("d: {1: 5}\na: {2020-01-01: 6}\n")
merged = confarg.merge(Config, files=[str(tmp / "base.yaml")], argv=[], env={})
for name in ("out.toml", "out.json", "out.yaml"):
    try:
        confarg.dump_file(merged, tmp / name)
        print(name, "-> written")
    except Exception as e:
        print(name, "->", f"{type(e).__name__}: {e}")

# expected: each written, or refused with a ConfargError naming the key
# actual:
#   out.toml -> TypeError: Invalid mapping key '1' of type 'int'. A string is required.
#   out.json -> TypeError: keys must be str, int, float, bool or None, not date
#   out.yaml -> written
```

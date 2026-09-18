# BUG-34 — YAML root config file with a non-dict top-level value silently loads empty

**Where:** `src/confarg/_files.py` (`_load_yaml`) · **Filed:** 2026-09-18
**Effort:** S · **Risk:** medium · **Impact:** behavior

A root YAML config file whose top-level value is a list or scalar silently loads as an
empty dict `{}`, while the equivalent JSON file raises `InvalidConfigFileError`. The
architecture note says `_LOADERS` is "a root configuration layer, must be a dict"
([02-files-and-env.md#format-dispatch-and-optional-dependencies](../../architecture/02-files-and-env.md#format-dispatch-and-optional-dependencies)),
so the silent swallow deviates from the documented intent. `_load_json` enforces this;
`_load_yaml` does not — it returns `data if isinstance(data, dict) else {}`. Fix: make
`_load_yaml` raise the same `InvalidConfigFileError` shape as `_load_json` on a non-dict
root, so both root loaders reject a non-dict top level loudly.

```python
# bug_repro.py — paste into a scratch dir and run
from pathlib import Path
import tempfile
from confarg._files import _load_yaml, _load_json

d = Path(tempfile.mkdtemp())

yp = d / "root.yaml"
yp.write_text("- 1\n- 2\n")  # top-level is a list
print("YAML list root ->", repr(_load_yaml(yp)))
# expected: InvalidConfigFileError (root config must be a dict, as with JSON)
# actual:   {}

jp = d / "root.json"
jp.write_text("[1, 2]")
try:
    _load_json(jp)
except Exception as e:
    print("JSON list root -> raises", type(e).__name__)
# JSON list root -> raises InvalidConfigFileError
```

```
$ python bug_repro.py
YAML list root -> {}
JSON list root -> raises InvalidConfigFileError
```

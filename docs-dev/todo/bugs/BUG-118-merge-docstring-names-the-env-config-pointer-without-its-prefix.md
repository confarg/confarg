# BUG-118 — `merge()`'s loading order names the env config pointer without its prefix

**Where:** `src/confarg/_api.py` (`merge`, *Config file loading order*), and the same list in
`src/confarg/_pipeline.py` (`_merge_sources`) · **Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** behavior

The published `merge()` docstring, which every adapter's `merge_*` refers to, lists step 3 as
"``CONFIG__*`` env vars" and gives "a global ``CONFIG=file``" as its example. The environment
channel only reads variables under `env_prefix`, though, and spells the segment after
`config_flag`, so the pointer is `<env_prefix>CONFIG[__<subpath>]`. A reader who sets `CONFIG`
next to `env_prefix="MYAPP_"` gets no file and no warning. `_merge_sources` writes
``<config_flag>__*``, which names the flag but still drops the prefix. Fix direction: spell it
`<env_prefix><CONFIG_FLAG>[__<subpath>]` in both lists, with `MYAPP_CONFIG=file` as the example.
`MergeOptions.config_flag` already spells it that way.

```console
$ grep -n "CONFIG" src/confarg/_api.py
94:        3. ``CONFIG__*`` env vars — sorted lexicographically by their env var name,
96:           A global ``CONFIG=file`` therefore loads before ``CONFIG__DB=db.yaml``,
97:           which loads before ``CONFIG__DB__HOST=host.yaml``.
```

```python
import dataclasses
import json
import os
import tempfile

import confarg


@dataclasses.dataclass
class Config:
    port: int = 0


path = os.path.join(tempfile.mkdtemp(), "app.json")
with open(path, "w") as f:
    json.dump({"port": 5432}, f)

print(confarg.load(Config, argv=[], env={"CONFIG": path}, env_prefix="MYAPP_"))
# documented: Config(port=5432)
# actual:     Config(port=0)
print(confarg.load(Config, argv=[], env={"MYAPP_CONFIG": path}, env_prefix="MYAPP_"))
# actual:     Config(port=5432) -- the spelling the channel reads
```

---
filed: 2026-10-06
where:
  - src/confarg/_cast.py::fold_root_json
effort: S
risk: high
impact: behavior
severity: critical  # the file's value comes back with no error
introduced_by: [PR-87, BUG-3]  # the CLI's root --json, then its environment twin
---
# BUG-186 — A root `json` cast swallows a field delete meant for the layers below

`--name-` deletes `name` from every layer below the CLI, so a file's `name` falls back to the
default. Beside a root `--json` cast it no longer does: `fold_root_json` merges the channel's
fields over the decoded object with `_deep_merge`, which spends the delete on the object's own
`name`, and the sentinel never reaches the merge with the files. The file's value comes back.
`<PREFIX>JSON` beside `<PREFIX>NAME-` does the same in the environment. Fix direction: the fold
keeps every delete the fields hold, so the channel's result still deletes in the layers under
it — as a whole-field delete with ops after it already does through the fold
([deep merge](../../architecture/pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it)).

Origin: latent since PR-87, which added the root `--json` flag and folded its object in under
the field flags inside the parse, `ctx.data = _deep_merge(base, ctx.data)` in vanilla and the
same `_deep_merge(decoded, result)` in the adapters' `apply_root_json`. `_deep_merge` is the
merge between layers, so it applied the field deletes to the decoded object there and dropped
them, before the parse result ever met the files. BUG-3 gave the environment its root cast with a
copy of that fold (`_parse_env._fold_root_json`); before it, `APP_JSON` was warned about and
ignored. REF-44 made the three copies one function, `_cast.fold_root_json`, unchanged. Bisected:
the CLI half reproduces from PR-87 on (`--json` was an unknown argument before it), the
environment half from BUG-3 on; today it reproduces on all five front-ends. No other open bug
names either origin.

```python
import tempfile
from dataclasses import dataclass
from pathlib import Path

import confarg


@dataclass
class Config:
    name: str = "default"


base = Path(tempfile.mkdtemp()) / "base.json"
base.write_text('{"name": "file"}')
print(confarg.load(Config, argv=["--name-"], files=[str(base)], env={}))
print(confarg.load(Config, argv=["--json", '{"name": "q"}', "--name-"], files=[str(base)], env={}))
env = {"APP_JSON": '{"name": "q"}', "APP_NAME-": ""}
print(confarg.load(Config, argv=[], files=[str(base)], env=env, env_prefix="APP_"))

# expected: Config(name='default') three times
# actual:   Config(name='default')
#           Config(name='file')
#           Config(name='file')
```

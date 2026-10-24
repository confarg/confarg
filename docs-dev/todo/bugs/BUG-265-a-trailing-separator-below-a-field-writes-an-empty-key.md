---
filed: 2026-10-21
where:
  - src/confarg/_parse_env.py::_parse_env
  - src/confarg/_parse_cli.py::_handle_unknown_field  # the CLI's "Missing field name after" refusal
effort: S
risk: low
impact: behavior
severity: minor  # loud at construction, but the error blames the value instead of the variable's spelling
introduced_by: [PR-5]  # the initial version splits the key on the separator and writes every segment, the empty one included
---

# BUG-265 — A trailing separator below a field writes an empty key the CLI refuses

`APP_PORT__=1` splits into `PORT` and an empty segment, and the environment writes the empty one as a key below `port`: the merged dict holds `{'port': {'': '1'}}`, and `build()` then refuses a dict where an `int` belongs, or an unknown field `''` below a struct field.
The CLI refuses the same spelling at parse time with its cause, `--app.port.` being "Missing field name after '--app.port.'".
Below a dict field both channels agree, and rightly: `APP_D__=1` and `--app.d. 1` set the key `''`, since a dict key may be empty.
Fix direction: the environment warns about an empty segment that names no dict key, with the cause the CLI refuses it with, as it warns where the CLI refuses an unknown field ([environment parsing](../../architecture/environment-parsing.md#environment-parsing)).
The bare prefix variable, an empty key *at the root*, is the separate case BUG-183 settled ([cli_prefix](../../architecture/cli-parsing/cli-prefix.md#the-bare-prefix-names-the-root)).

Origin: latent since the initial version (PR-5), whose `_parse_env` split the key on the separator and wrote every segment it got, the empty one included, while its CLI loop already refused the empty last segment of a flag.
The reproduction below gives the same output at PR-5 (with its `args=` keyword) and today.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Cfg:
    port: int = 0


print(confarg.merge(Cfg, argv=[], env={"APP_PORT__": "1"}, env_prefix="APP_"))
for kw in ({"env": {"APP_PORT__": "1"}, "env_prefix": "APP_"}, {"argv": ["--app.port.", "1"], "cli_prefix": "app"}):
    try:
        confarg.load(Cfg, **{"argv": [], "env": {}, **kw})
    except Exception as e:
        print(type(e).__name__, e)

# expected: a ConfargWarning naming the missing field after APP_PORT__, the variable ignored, as the CLI refuses --app.port.
# actual:
#   {'port': {'': '1'}}
#   TypeCoercionError Cannot coerce dict {'': '1'} to int at 'port'
#   UnknownArgumentError Missing field name after '--app.port.'
```

---
filed: 2026-10-06
where:
  - src/confarg/_parse_cli.py::_handle_scalar_root
  - src/confarg/cli/_build.py::_scalar_root_spec
  - src/confarg/exceptions.py::MissingFieldError
effort: M
risk: medium
impact: behavior
---
# BUG-177 — A collection root's bare flag takes one token, which construction refuses

On a list, set, tuple, namedtuple or dict root, `_handle_scalar_root` consumes exactly one
token after the bare `--<prefix>` and stores it as a string. Construction then refuses that
string whatever it holds, and a second token is refused as a stray positional. So the flag that
the missing-root remedy offers (`--app <value>`) never sets such a root; only `--app.json`
does. A field of the same type takes its run (`--xs 1 2`). The fix direction is to consume the
root's value as a field flag of its type does, writing at `__root__`, or else to make the remedy
name the root `json` cast for a collection root
([cli_prefix](../../architecture/cli-parsing/cli-prefix.md#cli_prefix),
[construction](../../architecture/types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).

```python
from dataclasses import dataclass

import confarg


@dataclass
class Cfg:
    xs: list[int]


print(confarg.load(Cfg, argv=["--xs", "1", "2"], env={}))
for argv in ([], ["--app", "1"], ["--app", "1", "2"]):
    try:
        print(confarg.load(list[int], argv=argv, env={}, cli_prefix="app"))
    except Exception as e:
        print(type(e).__name__, e)

# expected: [1] and [1, 2] for the last two, as the field takes them; the remedy names a flag
#   that sets the root
# actual:
#   Cfg(xs=[1, 2])
#   MissingFieldError No value provided for target type list[int]. Provide a value via CLI flag (--app <value>), environment variable, or config file.
#   TypeCoercionError Cannot construct list at '': expected list or dict with integer keys, got str '1'
#   UnknownArgumentError Unexpected positional argument: '2'. All arguments must be named flags (e.g. --fieldname value).
```

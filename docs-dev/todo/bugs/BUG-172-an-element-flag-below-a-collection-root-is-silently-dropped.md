---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_parse_cli
  - src/confarg/exceptions.py::MissingFieldError
effort: L
risk: medium
impact: config
---
# BUG-172 — An element flag below a collection root is silently dropped

On a non-struct root such as `list[Item]`, vanilla accepts `--app.0.size 1` and writes it at
the top of the merged dict (`{'0': {...}}`) instead of under `__root__`. `build()` reads only
`__root__`, so the value is lost without a word, and the four adapters refuse the same flag
because they never registered it. The [cli_prefix note](../../architecture/cli-parsing/cli-prefix.md#cli_prefix)
says `--<prefix> VALUE` is a scalar root's only CLI spelling, which points towards refusing it,
as BUG-115 proposes for the environment. Writing it under `__root__` as a patch is the other
option, so this needs a decision first. The missing-field remedy depends on that decision.
Below a collection root it offers `--0.size`, which the CLI reads as a positional and refuses,
and under a prefix it would name the flag that gets dropped
([construction](../../architecture/types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).

```python
from dataclasses import dataclass

import confarg


@dataclass
class Item:
    name: str
    size: int


print(confarg.merge(list[Item], argv=["--app.0.name", "a", "--app.0.size", "1"], env={}, cli_prefix="app"))
for argv, cli_prefix in ((["--app.0.name", "a", "--app.0.size", "1"], "app"), (["--json", '[{"name": "a"}]'], "")):
    try:
        confarg.load(list[Item], argv=argv, env={}, cli_prefix=cli_prefix)
    except Exception as e:
        print(type(e).__name__, e)

# expected: the element flags are refused, as the adapters refuse them, or written under
#   __root__; the remedy for '[0].size' names a spelling the CLI accepts
# actual:
#   {'0': {'name': 'a', 'size': 1}}
#   MissingFieldError No value provided for target type list[__main__.Item]. Provide a value via CLI flag (--app <value>), environment variable, or config file.
#   MissingFieldError Missing required field '[0].size' of type <class 'int'>. Set it via CLI (--0.size), environment variable, or config file.
```

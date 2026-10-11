---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_handle_unknown_field
  - src/confarg/_parse_cli.py::_handle_append_token
effort: S
risk: low
impact: behavior
---
# BUG-166 — An append below a dict key says the field does not exist

`--d.a.b 1` on a `dict[str, Any]` field is accepted: the walk types `d.a.b` as nothing, and
`_handle_unknown_field` takes the path as a key below the dict. The append spelling of the
same path, `--d.a.b+ 1`, reaches `_handle_unknown_field` too, but its `append_mode` branch
raises `UnknownArgumentError.no_such_field` first, so the message says field `d.a.b` was not
found, which a flag the same path takes contradicts. One segment up, `--d.a+ 1` is refused
for the right reason, by `_handle_append_token`: the key's type (`Any`) is no list, set or
frozenset. The env channel has no append spelling (FEAT-18), so the gap is the CLI's
diagnosis alone; both spellings are refused either way. Fix direction: below a dict, refuse
the append as `_handle_append_token` does, for a key whose type no declaration gives, rather
than as an unknown field. See
[collection patches](../../architecture/cli-parsing/collection-patches.md#collection-patch-operations) and
[type-guided parsing](../../architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions).

```python
from dataclasses import dataclass, field
from typing import Any

import confarg


@dataclass
class Cfg:
    d: dict[str, Any] = field(default_factory=dict)


for argv in (["--d.a.b", "1"], ["--d.a+", "1"], ["--d.a.b+", "1"]):
    try:
        print(argv, "->", confarg.merge(Cfg, argv=argv, env={}, config_flag=""))
    except confarg.exceptions.ConfargError as e:
        print(argv, "->", type(e).__name__, e)

# expected: `--d.a.b+` is refused as an append onto a key no type makes a collection, as `--d.a+` is
# actual:
#   ['--d.a.b', '1'] -> {'d': {'a': {'b': '1'}}}
#   ['--d.a+', '1'] -> ConfargError Cannot use + (append) syntax on '--d.a+': field 'd.a' has type typing.Any, which is not a list, set, or frozenset.
#   ['--d.a.b+', '1'] -> UnknownArgumentError Unknown argument: '--d.a.b+' (field 'd.a.b' not found)
```

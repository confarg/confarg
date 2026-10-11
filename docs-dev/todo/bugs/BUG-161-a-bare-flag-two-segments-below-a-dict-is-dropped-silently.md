---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_handle_unknown_field
  - tests/test_coverage_gaps.py::TestParseCLIBranches
effort: S
risk: low
impact: behavior
---
# BUG-161 — A bare flag two segments below a dict is dropped silently

A flag with no value is refused by `_require_value` ("a value-taking flag always needs its
value"), and `--d.a` on a `dict[str, Any]` field is: the walk resolves `d.a` to the dict's
value type. One segment deeper, `--d.a.b` resolves to nothing and lands in
`_handle_unknown_field`, which takes it as a key below the dict but consumes its value only
if one is there: with none, the flag vanishes without a word, and the next flag is parsed as
if it had never been typed. vanilla, argparse and cyclopts drop it; click and typer exit with
their own usage error first (BUG-96). Fix direction: ask `_require_value` in the dict branch
of `_handle_unknown_field`, as every other value-consuming branch does, and drop
`TestParseCLIBranches.test_dict_at_path_bare_flag`, which pins the drop. See
[token consumption](../../architecture/cli-parsing/token-consumption.md#token-consumption) and
[type-guided parsing](../../architecture/cli-parsing/type-guided-parsing.md#type-guided-parsing).

```python
from dataclasses import dataclass, field
from typing import Any

import confarg


@dataclass
class Cfg:
    d: dict[str, Any] = field(default_factory=dict)


for argv in (["--d.a"], ["--d.a.b"], ["--d.a.b", "--d.k", "1"]):
    try:
        print(argv, "->", confarg.merge(Cfg, argv=argv, env={}, config_flag=""))
    except confarg.exceptions.ConfargError as e:
        print(argv, "->", type(e).__name__, e)

# expected: `--d.a.b` with no value is refused as `--d.a` is
#   ['--d.a.b'] -> ConfargError Missing value for '--d.a.b'. Usage: --d.a.b <value>
# actual:
#   ['--d.a'] -> ConfargError Missing value for '--d.a'. Usage: --d.a <value>
#   ['--d.a.b'] -> {}
#   ['--d.a.b', '--d.k', '1'] -> {'d': {'k': '1'}}
```

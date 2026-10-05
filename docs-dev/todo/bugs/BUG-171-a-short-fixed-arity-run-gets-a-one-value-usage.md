---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_consume_fixed_tuple_args
  - src/confarg/exceptions.py::ConfargError  # missing_value
effort: S
risk: medium
impact: behavior
---
# BUG-171 — A short token run on a fixed-arity flag gets a one-value usage line

A fixed-arity flag given fewer tokens than its arity is refused as a missing value, as
[token consumption](../../architecture/cli-parsing/token-consumption.md#token-consumption)
intends: `_consume_fixed_tuple_args` asks `_require_value` once per position. But it passes no
`usage`, so the message ends with the default `Usage: --pair <value>`, which describes a
one-value flag. A user who passed `--pair 1` to a `tuple[int, int]` field is told to pass one
value, which is what they did. argparse (`argument --pair: expected 2 arguments`) and click
(`Option '--pair' requires 2 arguments.`) both name the count. Fix direction: pass a usage
spelling one placeholder per position (`<value> <value>`, or the namedtuple's field names),
through the `usage` parameter `missing_value` already takes for the JSON cast.

```python
from dataclasses import dataclass
from typing import NamedTuple

import confarg


class Pt(NamedTuple):
    x: int
    y: int


@dataclass
class Cfg:
    pair: tuple[int, int] = (0, 0)
    pt: Pt = Pt(0, 0)


for argv in (["--pair", "1"], ["--pt", "1"]):
    try:
        print(argv, "->", confarg.load(Cfg, argv=argv, env={}))
    except confarg.exceptions.ConfargError as e:
        print(argv, "->", type(e).__name__, e)

# expected: a usage line naming two values, e.g. Usage: --pair <value> <value>
# actual:
#   ['--pair', '1'] -> ConfargError Missing value for '--pair'. Usage: --pair <value>
#   ['--pt', '1'] -> ConfargError Missing value for '--pt'. Usage: --pt <value>
```

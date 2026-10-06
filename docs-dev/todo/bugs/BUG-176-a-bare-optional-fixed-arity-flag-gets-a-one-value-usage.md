---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_union_seq_value
  - src/confarg/_parse_cli.py::_fixed_arity_usage
effort: S
risk: low
impact: behavior
severity: minor
introduced_by: [PR-77]  # fix: Various fixes to CLI integration, which wrote the union path's missing-value refusal
---
# BUG-176 — A bare optional fixed-arity flag gets a one-value usage line

BUG-171 made a fixed-arity flag's missing value spell every position (`Usage: --pair <value>
<value>`, `Usage: --pt <x> <y>`). An `Optional` fixed-arity field is a union with a sequence
variant as resolved, so its bare occurrence is refused by `_union_seq_value` instead, which
passes no usage. The message still ends with `Usage: --pair <value>`, describing a one-value
flag to a user whose field wants two values. The one value it does take is a none word
(`--pair none`, BUG-163), which the line does not mention. Fix direction: when the union has no
scalar variant other than `None`, spell the sequence variant through `_fixed_arity_usage`,
possibly beside the none word. The union path has more than one variant, so which spelling
reads best is open. See
[token consumption](../../architecture/cli-parsing/token-consumption.md#token-consumption) and
[whole-value flags](../../architecture/cli-adapters/whole-value-flags.md#whole-value-flags).

Origin: latent since PR-77, which wrote `_union_seq_value`'s missing-value refusal with a fixed
`<value>` usage. Before BUG-171 a plain fixed-arity field read `<value>` too; that fix gave it one
placeholder per position through `_fixed_arity_usage` and did not route the union path through it.

```python
from dataclasses import dataclass
from typing import NamedTuple

import confarg


class Pt(NamedTuple):
    x: int
    y: int


@dataclass
class Cfg:
    pair: tuple[int, int] | None = None
    pt: Pt | None = None


for argv in (["--pair"], ["--pt"]):
    try:
        print(argv, "->", confarg.load(Cfg, argv=argv, env={}))
    except confarg.exceptions.ConfargError as e:
        print(argv, "->", type(e).__name__, e)

# expected: a usage line naming both positions, e.g. Usage: --pair <value> <value>
# actual (the same on all five front-ends):
#   ['--pair'] -> ConfargError Missing value for '--pair'. Usage: --pair <value>
#   ['--pt'] -> ConfargError Missing value for '--pt'. Usage: --pt <value>
```

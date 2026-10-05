---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_advance_field_type  # the LIST / SET / FROZENSET case
  - src/confarg/typedload/_construct.py::_build_items
effort: S
risk: medium
impact: behavior
---
# BUG-170 — A list segment spelled as a merge sentinel writes the sentinel

The walk steps from a list into its element type whatever the segment spells, so `--xs.* 5`
and `--xs.+ 1` are typed as an element and written as `{'*': 5}` and `{'+': 1}`: the user's
segment lands in the merge's own vocabulary. `'*'` then reaches `_build_items` as a base list
that is an int and escapes as a raw `TypeError`, no `ConfargError`; `'+'` reads as an append of
a scalar. An empty segment, `--xs. 1`, takes the same step and is refused only at build, as
"dict keys must be integer indices", where a struct field gets the parse-time "Missing field
name after '--sub.'". Fix direction: refuse below a list a segment no list patch spells, at the
walk, so registration and the loop agree; a dict keeps such keys, which build as keys there.
See [deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics) and
[FEAT-3](../features/FEAT-3-reserved-sentinel-key-registry.md), the general guard.

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class Cfg:
    xs: list[int] = field(default_factory=lambda: [7])


for argv in (["--xs+", "1"], ["--xs.+", "1"], ["--xs.*", "5"]):
    try:
        print(argv, "->", confarg.merge(Cfg, argv=argv, env={}, config_flag=""), confarg.load(Cfg, argv=argv, env={}, config_flag=""))
    except Exception as e:
        print(argv, "->", type(e).__name__, e)

# expected: `--xs.+` and `--xs.*` refused at parse as segments no list takes, a ConfargError
# actual:
#   ['--xs+', '1'] -> {'xs': {'+': [1]}} Cfg(xs=[1])
#   ['--xs.+', '1'] -> {'xs': {'+': 1}} Cfg(xs=[1])
#   ['--xs.*', '5'] -> TypeError 'int' object is not iterable
```

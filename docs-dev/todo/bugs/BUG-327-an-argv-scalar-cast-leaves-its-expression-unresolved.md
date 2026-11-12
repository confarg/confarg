---
filed: 2026-11-12
where:
  - src/confarg/_cast.py::resolve_forced_value  # an argv scalar cast stores a _Pinned
  - src/confarg/dictexpr/_expressions.py::_collect_expressions  # resolution walks dicts and lists, never a _Pinned
  - src/confarg/dictexpr/_expressions.py::escape_data  # BUG-326's escape treats a _Pinned as resolution does
  - src/confarg/_types.py::_Pinned
effort: M  # whether a cast's value resolves, and how an expression meets an eager .int cast
needs_design: true
risk: high  # the expression engine, every front-end's argv
impact: config  # an argv cast holding ${...} would start being evaluated
severity: critical  # argv and a file spell one cast and build different values, with no error
introduced_by: [PR-50]
---

# BUG-327 — An argv scalar cast leaves its expression unresolved

`--f.str 'at ${x}'` builds the text `at ${x}`, while a file's `{__cast__: str, __value__: 'at ${x}'}` and `--f.json '"at ${x}"'` build `at 7`.
An argv scalar cast is stored as a `_Pinned` (`_cast.resolve_forced_value`), which resolution's walk never enters (`_collect_expressions` walks dicts and lists), so its value is neither evaluated nor unescaped: `--f.str 'at $${x}'` builds `at $${x}`, where a file builds `at ${x}`.
A file's cast is still a plain dict when resolution runs, and becomes a pin only at construction.
`--f.int '${x}'` is refused, `Cannot coerce str '${x}' to int at 'f'`, though the deferral rule says no gate before `build()` may refuse an expression ([deferral rule](../../architecture/expressions/deferral-rule.md#deferral-rule)).

The replay dump inherits it: `resolve()` hands the pin back as it stands, and `dump_file()` writes it as `{__cast__: str, __value__: 'at ${x}'}`, which the reload evaluates.
BUG-326's escape (`escape_data`) and `from_dict()`'s reading of an escape treat a `_Pinned` as resolution does, opaque, so the fix here changes them with it.

Fix direction: the design pass decides whether a cast's value resolves before the cast applies, on every channel alike (a pin resolution walks into, or a cast stored as the file's dict until construction), and what `.int` makes of an expression that resolves to an int.
See [casts](../../architecture/cli-parsing/casts-and-reserved-words.md#force-casts) and [the stealing rule](../../architecture/types/stealing-rule.md#cast-pinning-in-files).

Origin: a regression from PR-50 (Enum priority in the stealing rule), which wrapped an argv cast's value in a `_Pinned` so that construction would not steal it; until then the initial version (PR-5) stored `--f.str`'s value as a plain string, which resolution read.

```python
from dataclasses import dataclass
from pathlib import Path

import confarg


@dataclass
class C:
    f: str | int = 0
    x: int = 7


Path("in.yaml").write_text("f: {__cast__: str, __value__: 'at ${x}'}\n", encoding="utf-8")
print(confarg.load(C, argv=[], files=["in.yaml"]))
print(confarg.load(C, argv=["--f.str", "at ${x}"]))
print(confarg.load(C, argv=["--f.str", "at $${x}"]))
# expected: C(f='at 7', x=7)
#           C(f='at 7', x=7)
#           C(f='at ${x}', x=7)
# actual:   C(f='at 7', x=7)
#           C(f='at ${x}', x=7)
#           C(f='at $${x}', x=7)
```

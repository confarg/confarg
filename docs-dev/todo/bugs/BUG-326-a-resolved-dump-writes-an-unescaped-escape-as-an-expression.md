---
filed: 2026-11-11
where:
  - src/confarg/_api.py::resolve  # resolution takes one `$` off every escape
  - src/confarg/_api.py::dump_file  # writes a dict as it stands
  - src/confarg/dictexpr/_expressions.py::escape_data  # what spells a dict so that resolution gives it back
effort: M  # the design is which dict is escaped, since dump_file cannot tell a resolved dict from a merged one
needs_design: true  # a flag on dump_file, resolve() handing back an escaped document, or a recorded boundary
risk: medium  # every string a replay dump writes; a merged dict must stay verbatim
impact: behavior  # an escaped text in a configuration replays as that text
severity: critical  # the replay silently computes another value, as BUG-318 did for the object dump
introduced_by: [PR-5]
---

# BUG-326 — A resolved dump writes an unescaped escape as an expression

`f: at $${x}` loads as the text `at ${x}`, but `dump_file(resolve(C, merged))` writes `f: at ${x}`, which the replay evaluates: it reads whatever `x` holds, or fails on a missing reference.
Resolution takes one `$` off every escape, and `dump_file()` writes a dict as it stands ([the object dump writes state](../../architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)), so the resolved dict, the one meant for replaying a run, is the only dump that loses the escape.
`dump()` escapes every string value of an object dump with `escape_data` since BUG-318 ([serialization](../../architecture/types/serialization.md#text-spelling-an-expression-is-written-escaped)); the merged dict keeps its escapes, written as the user wrote them.

Fix direction: `dump_file()` cannot tell a resolved dict from a merged one, and `from_dict(C, resolve(C, merged))` must keep reading the text, so the design pass picks between a `dump_file()` option that escapes, `resolve()` handing back a dict that `dump_file()` knows as resolved, and a recorded boundary in [limitations](../../architecture/limitations.md).
OmegaConf has the same bug: `to_yaml(cfg, resolve=True)` writes `${x}` for a `\${x}`, and the reload reads the value of `x` (run).

Origin: latent since the initial version (PR-5), which brought `resolve()`, the `$${...}` escape and a `dump_file()` writing a dict as it stands together.

```python
from dataclasses import dataclass
from pathlib import Path

import confarg


@dataclass
class C:
    f: str = ""
    x: int = 7


Path("in.yaml").write_text("f: at $${x}\n", encoding="utf-8")
merged = confarg.merge(C, argv=[], files=["in.yaml"])
confarg.dump_file(confarg.resolve(C, merged), "replay.yaml")
print(confarg.load(C, argv=[], files=["in.yaml"]))
print(confarg.load(C, argv=[], files=["replay.yaml"]))
# expected: C(f='at ${x}', x=7)
#           C(f='at ${x}', x=7)
# actual:   C(f='at ${x}', x=7)
#           C(f='at 7', x=7)
```

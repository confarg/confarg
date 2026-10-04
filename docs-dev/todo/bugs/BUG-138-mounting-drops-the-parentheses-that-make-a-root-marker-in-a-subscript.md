# BUG-138 — Mounting drops the parentheses that make a root marker in a subscript

**Where:** `src/confarg/dictexpr/_expressions.py` (`_prefix_content`, `_unparse`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** high · **Impact:** behavior

Inside a subscript `::` is a slice step, so a root reference there is spelled in parentheses,
`items[(::step)]`
([reference-anchoring.md#implementation-constraints](../../architecture/expressions/reference-anchoring.md#implementation-constraints)).
A file mounted below the root is prefixed on the tree and unparsed, and `ast.unparse` keeps no
parentheses it does not need for Python. So the fragment's `${items[(::step)]}` comes out as
`${db.items[::step]}`, which reads as a slice and which validation refuses. The same value
at the root resolves. Fix direction: when `_unparse` writes a root stand-in whose innermost
enclosing bracket is a subscript's `[`, it wraps that operand in parentheses again. This is the
rule `_anchor_markers` reads, run the other way.

```python
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import confarg


@dataclass
class Db:
    items: dict[str, int]
    p: int


@dataclass
class Config:
    step: str
    db: Db


d = Path(tempfile.mkdtemp())
(d / "db.json").write_text(json.dumps({"items": {"k": 1}, "p": "${items[(::step)]}"}))
(d / "main.json").write_text(json.dumps({"step": "k", "db": {"__include__": "db.json"}}))

merged = confarg.merge(Config, files=[str(d / "main.json")], argv=[])
print(merged["db"]["p"])
try:
    print(confarg.resolve(merged)["db"]["p"])
except confarg.exceptions.ConfargError as exc:
    print(type(exc).__name__, exc)
# expected: ${db.items[(::step)]} then 1, as the same value at the root reads items['k']
# actual:
# ${db.items[::step]}
# UnsafeExpressionError Disallowed construct in expression: Slice
```

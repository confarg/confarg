---
filed: 2026-11-07
where:
  - src/confarg/typedload/_coerce.py::read_as_object  # reads a value holding ${ as written
  - src/confarg/_typed_read.py::_read_leaf  # the same gate before a union's reading
  - src/confarg/_typed_read.py::_computes  # the same gate for a tagged leaf, kept alike until this lands
effort: S  # the fix is three gates; the work is showing no read meets a pending expression
risk: medium  # if some read path does meet one, a registered coercer builds the raw text into an object
impact: behavior  # an expression over an escaped literal reads the object construction builds
severity: critical  # `${p == q}` is False where the built p == q is True, with no error
introduced_by: [BUG-246]  # PR-441 read a typed leaf as its object, deferring a value contains_expression matches
---

# BUG-310 — An expression reads an escaped literal at a typed leaf as text

A typed leaf written with an escape, `p: $${HOME}`, builds `Path('${HOME}')`, but an expression reads it as the `str` `'${HOME}'`: `${p == q}` against a `Path('${HOME}')` is `False`, and `${p / 'a'}` fails on two strings, against [a typed leaf reads as its object](../../architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object).
Resolution unescapes `$${HOME}` to the literal before anything reads it, and the reading's gate, `contains_expression(value)` in `read_as_object`, takes that literal for an expression yet to resolve and reads it as written.
The [deferral rule](../../architecture/expressions/deferral-rule.md#deferral-rule) is written for gates that run before `build()`; the reading runs during resolution, after the value it reads has resolved *(inferred: every reference waits for what it reaches, but no test pins that the reader is never handed a pending expression, the locals namespace and a partial `resolve()` included)*.
The same gate stands before a union's reading in `_typed_read._read_leaf`, and in `_typed_read._computes`, which reads a tagged registered leaf holding a literal `${` as its dict (BUG-283 kept it alike).

Fix direction: show that every read sees resolved values, then drop the gate at the three sites, so a literal reads as the object construction builds from it; `_computes` keeps refusing a `call:` or `bind:`.

Origin: latent since BUG-246, which made an expression read an Enum or registered leaf as its object and deferred a value holding an expression with the predicate every pre-`build()` gate uses, which also matches the literal an escape resolves to.

```python
from dataclasses import dataclass
from pathlib import Path

import confarg
import confarg.exceptions


@dataclass
class Config:
    p: Path = Path()
    q: Path = Path("${HOME}")
    out: str = ""
    same: bool = False


c = confarg.build(Config, {"p": "$${HOME}", "same": "${p == q}"})
print(repr(c.p), c.p == c.q, c.same)
try:
    print(confarg.build(Config, {"p": "$${HOME}", "out": "${str(p / 'a')}"}).out)
except confarg.exceptions.ConfargError as e:
    print(type(e).__name__, e)
# expected: WindowsPath('${HOME}') True True
#           ${HOME}\a
# actual:   WindowsPath('${HOME}') True False
#           ExpressionEvalError Error in expression "${str(p / 'a')}": unsupported operand type(s) for /: 'str' and 'str'
```

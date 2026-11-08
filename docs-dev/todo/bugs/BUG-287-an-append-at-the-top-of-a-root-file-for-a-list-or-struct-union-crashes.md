---
filed: 2026-10-25
where:
  - src/confarg/_default_layer.py::lay_defaults  # settles the root's pending ops into a list where the root must stay a dict
  - src/confarg/_default_layer.py::_applied_over_nothing
  - src/confarg/_typed_merge.py::_MixedRootAt  # left_beside keeps a root-level ListOp beside a field write, drops it under a whole one
effort: S
risk: medium  # the default layer feeds expression resolution and construction alike
impact: behavior
severity: minor  # a raw AttributeError, but `__root__: [1]` or `__root__: {__append__: [1]}` spells the same root
introduced_by: [PR-458]  # BUG-219/220: read a pending list op as its list
---

# BUG-287 — An append at the top of a root file for a list-or-struct union crashes

A root file holding `__append__: [1]` at its top, for a root `list[int] | A`, crashes `load()` with `AttributeError: 'list' object has no attribute 'items'` in `dictexpr._expressions._scan_expressions`.
The same op one level down, on a field `f: list[int] | A`, builds `[1]`, and so does the root file `__root__: {__append__: [1]}`.
The default layer applies the root's pending ops over nothing (`_applied_over_nothing`) and hands expression resolution a list where the merged root is always a dict.
Fix direction: decide what a pending op at the top of a mixed root ([a mixed root](../../architecture/cli-parsing/cli-prefix.md#a-mixed-root-is-set-whole-or-by-field)) is: the whole value's op, read as `__root__` holding it, or a key no variant reads, refused naming it.
The answer also settles what `_MixedRootAt.left_beside` does with such a key, kept beside a field write and dropped under a whole one today, and what a plain `list[int]` root does with the same file, which builds nothing and reports `MissingFieldError` as if no value had been supplied.

Origin: a regression from PR-458 (BUG-219, BUG-220), which read a pending list op as the list it makes, so that an expression reading one sees a list, and applied the ops over nothing in the default layer; its parent built `[1]` from this file.
It applied them at every node, the root included, where `resolve_expressions` walks a dict.

```python
import pathlib
import tempfile
from dataclasses import dataclass

import confarg


@dataclass
class A:
    a: int = 0


@dataclass
class Cfg:
    f: list[int] | A = 0


d = pathlib.Path(tempfile.mkdtemp())
(d / "root.yaml").write_text("__append__: [1]\n")
(d / "field.yaml").write_text("f:\n  __append__: [1]\n")
print(confarg.load(Cfg, files=[str(d / "field.yaml")], argv=[], env={}))
# Cfg(f=[1])
print(confarg.load(list[int] | A, files=[str(d / "root.yaml")], argv=[], env={}))
# expected: [1], as the field builds, or a ConfargError naming the key
# actual:   AttributeError: 'list' object has no attribute 'items'
```

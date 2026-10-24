---
filed: 2026-10-13
where:
  - src/confarg/typedload/_construct.py::_import_class_by_path
effort: S
risk: medium  # only a file can write a tag that is no string; argv and the environment always give text
impact: behavior
severity: minor  # invalid input answered with a raw exception
introduced_by: [PR-5]  # the tag was read as a dotted path without checking it is a string
---

# BUG-235 — A union tag that is no string escapes `build()` as a raw `AttributeError`

A file that writes the union tag as a number, a list or null, `{class: 3}`, reaches `_import_dotted`, which calls `.split(".")` on it, so `build()` fails with Python's `AttributeError: 'int' object has no attribute 'split'` instead of a `TypeCoercionError` naming the field and the tag.
Every route that reads a tag goes through `_import_class_by_path` (a union's tag and a struct field's subclass tag), so the fix belongs there, at the one reader: refuse a tag that is no string with a message naming the key and the path.
See [dotted imports](../../architecture/types/dotted-imports.md#dotted-imports).

Origin: latent since the initial version (PR-5); the reproduction fails the same way there.
The tag has always been read as a dotted path, and argv and the environment, which only give text, never reach the case.

```python
from dataclasses import dataclass

import confarg


@dataclass
class A:
    a: int = 0


@dataclass
class B:
    b: int = 0


@dataclass
class Config:
    x: A | B | None = None


try:
    print(confarg.from_dict(Config, {"x": {"class": 3}}))
except Exception as e:
    print(f"{type(e).__name__}: {e}")

# expected: TypeCoercionError naming the 'class' tag at 'x' and saying it must be a dotted path string
# actual:   AttributeError: 'int' object has no attribute 'split'
```

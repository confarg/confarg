---
filed: 2026-10-16
where:
  - src/confarg/typedload/_coerce.py::_is_eagerly_coercible
  - src/confarg/typedload/_coerce.py::_try_coerce
  - src/confarg/typedload/_coerce.py::_LEAF_SERIALIZERS  # Path dumps through str, with the OS's separators
  - src/confarg/_api.py::_resolve_over_defaults
  - src/confarg/dictexpr/_expressions.py::_resolve_single
effort: L
risk: high
impact: config  # `${p / 'sub'}` works from argv, env and the default today
severity: critical  # the same configuration resolves to another value by channel, with no error
introduced_by: [PR-5]  # the initial _try_coerce coerced Enum and Path tokens, and no file string
---
# BUG-246 — An Enum or registered leaf reads typed from argv and env, and as text from a file

`_try_coerce` coerces a token eagerly for an `Enum` or a registered leaf type (`Path` among them), "so the merged dict has consistent types regardless of source", but a file's string is never coerced before construction ([token model](../../architecture/types/token-model.md#token-model)). So an expression reads `Color.RED` or `Path('/b')` from argv, env and the default layer, and `'red'` or `'/b'` from a file: an interpolation writes `Color.RED` (and the OS's separators) on three channels and what was written on the fourth, `${c == 'red'}` flips with the channel, and `${p / 'sub'}` fails from a file only. The same holds below a list, a tuple and an optional. Fix direction, settled: `merge()` holds what was written on every channel, `build()` and `resolve()` read such a leaf as its object wherever a single type is certain, and an object takes its dump form wherever it leaves an expression, never `str()`. A `Path` dumps as `as_posix()`.

Origin: latent since the initial version (PR-5), whose `_try_coerce` coerced `Enum` and `Path` tokens while files kept their native values; `register_leaf_type` later extended the eager set to every registered type.

```python
import enum
import pathlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

import confarg


class Color(enum.Enum):
    RED = "red"


@dataclass
class Config:
    p: Path = Path("/a")
    c: Color = Color.RED
    tag: str = ""


file = pathlib.Path(tempfile.mkdtemp(), "config.yaml")
file.write_text("p: /b\nc: red\n")
expr = ["--tag", "${c}@${p}"]
print("argv:", confarg.load(Config, argv=["--p", "/b", "--c", "red", *expr], env={}).tag)
print("file:", confarg.load(Config, argv=expr, env={}, files=[file]).tag)
# expected: the same tag from both channels
# actual (Windows):
#   argv: Color.RED@\b
#   file: red@/b
```

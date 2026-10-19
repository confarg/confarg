---
filed: 2026-10-18
where:
  - src/confarg/_import.py::_import_dotted
effort: S
risk: low  # the message only; which exception is raised stays
impact: none
severity: minor  # the error is raised and names the cause; only the module it names is wrong
introduced_by: [PR-22]  # the broken-module message names the prefix being imported
---

# BUG-256 — A module that fails while imported is named by the path being tried, not by the module

`_import_dotted` imports the longest prefix of a dotted path first, so for `brokenmod.Thing` it calls `import_module("brokenmod.Thing")`, which runs `brokenmod` itself.
When `brokenmod` raises, the error names the prefix tried, `error loading module 'brokenmod.Thing'`, though `brokenmod.Thing` is the class and `brokenmod` the module that failed.
Every reader of a dotted path repeats it: a `type` field, a class tag, a `bind:` or `call:` target.
Fix direction: name the module that raised rather than the prefix tried, for instance by importing a path's ancestors before the path, so the first import that fails is the module's own; see [a path names nothing, or a module fails](../../architecture/types/dotted-imports.md#a-path-names-nothing-or-a-module-fails).
Found while fixing BUG-235.

The same branch wraps the interpreter's own errors: an import that runs out of stack, a few frames below the recursion limit, is reported as a module that fails, `error loading module 'freshmod.Thing': maximum recursion depth exceeded`, though `freshmod` is sound.
Since BUG-248 no configuration recurses that deep, but a caller's stack still can; a `RecursionError` or a `MemoryError` should pass through unwrapped (second snippet below).
Found while fixing BUG-248.

Origin: latent since PR-22, which added the `except Exception` branch reporting a module that fails while imported, by the prefix the loop was trying; REF-5 added the same message for a missing dependency.

```python
import pathlib
import sys
import tempfile
from dataclasses import dataclass

import confarg

pkg = pathlib.Path(tempfile.mkdtemp())
(pkg / "brokenmod.py").write_text("raise RuntimeError('boom')\n")
sys.path.insert(0, str(pkg))


@dataclass
class Config:
    t: type | None = None


try:
    confarg.from_dict(Config, {"t": "brokenmod.Thing"})
except Exception as e:
    print(f"{type(e).__name__}: {e}")

# expected: ... error loading module 'brokenmod': boom
# actual:   SymbolImportError: Cannot import class 'brokenmod.Thing' at 't': Cannot import 'brokenmod.Thing': error loading module 'brokenmod.Thing': boom
```

```python
import pathlib
import sys
import tempfile
from dataclasses import dataclass

import confarg

pkg = pathlib.Path(tempfile.mkdtemp())
(pkg / "freshmod.py").write_text("class Thing:
    pass
")
sys.path.insert(0, str(pkg))


@dataclass
class Config:
    t: type | None = None


def called_from(frames, fn):
    return fn() if frames == 0 else called_from(frames - 1, fn)


try:
    called_from(sys.getrecursionlimit() - 30, lambda: confarg.from_dict(Config, {"t": "freshmod.Thing"}))
except Exception as e:
    print(f"{type(e).__name__}: {e}")

# expected: RecursionError: maximum recursion depth exceeded
# actual:   SymbolImportError: Cannot import class 'freshmod.Thing' at 't': Cannot import 'freshmod.Thing': error loading module 'freshmod.Thing': maximum recursion depth exceeded
```

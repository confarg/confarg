---
filed: 2026-10-24
where:
  - src/confarg/_import.py::dotted_name  # spells __module__, the module that defines the object
effort: S
needs_design: true  # the effort sizes the design pass: which public path names a re-exported callable
risk: medium  # the spelling of every dumped callable and class tag goes through it
impact: config  # a dumped file's paths change spelling
severity: critical  # a dump made on one platform loads elsewhere as another function, with no error
introduced_by: [PR-5]  # the initial version writes a callable as __module__ plus __qualname__
---

# BUG-279 — A dumped callable names the platform module that defines it, not the public one

`dotted_name` spells a callable by its `__module__`, which is where it is defined, and the `os` functions are defined in a platform module: on Windows `os.getcwd` dumps as `nt.getcwd` and `os.path.join` as `ntpath.join` (`posix` and `posixpath` elsewhere).
The path imports back, so `dump()` accepts it, but the file is tied to the platform that wrote it.
Loaded on Linux, `nt.getcwd` is refused, since there is no `nt` module; `ntpath.join` imports, and joins with Windows separators, so the configuration means another function than the one it was dumped from, with no error.
`pickle` writes the same (`ntpath`, `join`) and is not portable either.
Design question: the spelling the user wrote is gone by dump time, so the choice is among looking for a public module re-exporting the same object (`os.getcwd is nt.getcwd`, a heuristic over which modules to try), recording the spelling a callable was read from (a stamp, which [an object dumps the state it holds](../../architecture/callables.md#an-object-dumps-the-state-it-holds) rejects for objects), or documenting the boundary in [limitations](../../architecture/limitations.md#callables-and-serialization).
Found while weighing the review of BUG-195's fix, which names C methods through the same `dotted_name`.

Origin: latent since the initial version (PR-5), which wrote a callable as `__module__` plus `__qualname__`; it dumps `ntpath.join` there as now.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class F:
    fn: Callable


for path in ["os.getcwd", "os.path.join", "os.stat"]:
    print(path, "->", confarg.dump(confarg.build(F, {"fn": path}))["fn"])

# expected: os.getcwd -> os.getcwd, os.path.join -> os.path.join, os.stat -> os.stat
# actual (Windows):
# os.getcwd -> nt.getcwd
# os.path.join -> ntpath.join
# os.stat -> nt.stat
```

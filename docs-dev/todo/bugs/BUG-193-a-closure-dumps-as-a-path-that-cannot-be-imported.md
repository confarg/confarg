---
filed: 2026-10-07
where:
  - src/confarg/_callable.py::_serialize_callable
effort: S
risk: low
impact: behavior
severity: minor  # dump() succeeds and the read-back fails loudly; the merged dict saves the config
introduced_by: [PR-5]  # the initial version writes module + qualname for any callable that has both
---
# BUG-193 — A closure or a lambda dumps as a path that cannot be imported

`_serialize_callable` writes any callable carrying `__module__` and `__qualname__` as their
dotted join. A closure's qualified name holds `<locals>`, and a lambda's `<lambda>`, so the
dump succeeds with a path no import resolves. The error only comes when the file is read back.
A callable that no configuration spells cannot be dumped from the object
([limitations](../../architecture/limitations.md#callables-and-serialization)), and `dump()`
should say so where it happens. One way to check is to import the path back and compare with
`is`, in the spirit of `_serialize._reads_back`. It catches every unimportable or shadowed name,
not only the two markers.

Origin: the initial version took "has a module and a qualified name" to mean "importable by
that name", which nested and anonymous functions break. Latent since then. BUG-191 makes it
more common: once a `call:` result dumps as what it is, every factory returning a closure
reaches this path. BUG-195 shares the origin from the other side: the same check refuses a
builtin method descriptor, which has no `__module__` but does have an importable path.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


def make_joiner(sep: str) -> Callable[[str], str]:
    def join(s: str) -> str:
        return sep.join(s)
    return join


@dataclass
class Config:
    f: Callable[[str], str]


dumped = confarg.dump(Config(f=make_joiner("-")))
print(dumped)
# expected: an error at dump(), naming the closure as having no configuration spelling
# actual:   {'f': '__main__.make_joiner.<locals>.join'}, refused only when read back:
confarg.from_dict(Config, dumped)
# confarg.exceptions.SymbolImportError: Cannot import '__main__.make_joiner.<locals>.join':
#     'function' object has no attribute '<locals>'
```

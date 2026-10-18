---
filed: 2026-10-07
where:
  - src/confarg/_callable.py::_serialize_callable
  - src/confarg/_import.py::dotted_name
effort: S
risk: low
impact: behavior
severity: minor  # dump() refuses loudly; dumping the merged dict saves the configuration
introduced_by: [PR-5]  # the initial version requires __module__ of any callable it writes as a path
---
# BUG-195 — A builtin method descriptor loads from its path but cannot be dumped

A Callable field accepts `"str.upper"` and keeps the C method descriptor as it is
([auto-binding](../../architecture/callables.md#auto-binding)), but `dump()` refuses the value
it built. `_serialize_callable` writes a callable as a path only when it has `__module__`, and a
descriptor of a C type has none: `str.upper`, `dict.get`, the slot wrapper `int.__add__` and the
builtin class method `dict.fromkeys` all fail the same way. A reference to code dumps as its
dotted path ([the object dump writes state](../../architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)),
and the descriptor names its owner through `__objclass__` (`__self__` for the class method), so
`dotted_name`, the one writer of a path, can spell `builtins.str.upper`, which the import reads
back.

Origin: the initial version took a callable without `__module__` to be an instance no spec
built, and wrote the error message for that case. Latent since then. The builtins fallback of
PR-91 made the short path `str.upper` load, but `builtins.str.upper` loaded before it *(inferred)*
and fails to dump the same way. BUG-193 shared the origin from the other side, the same check letting
an unimportable closure through as a path; its fix imports every path back before writing it
([round-trip](../../architecture/callables.md#a-path-is-written-only-when-it-reads-back)), so the
path `dotted_name` derives for a descriptor is checked the same way.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    f: Callable[[str], str]


config = confarg.build(Config, {"f": "str.upper"})
print(config.f("abc"))  # ABC
print(confarg.dump(config))
# expected: {'f': 'builtins.str.upper'}
# actual:   confarg.exceptions.ConfargError: Cannot serialize callable <method 'upper' of 'str'
#     objects>: no __module__/__qualname__ available. For class instances, ensure the instance
#     was constructed via confarg (which stores the spec for round-trip serialization).
```

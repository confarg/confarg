---
filed: 2026-10-05
where:
  - src/confarg/typedload/_construct.py::_missing_field_error
  - src/confarg/typedload/_construct.py::construct
effort: L
risk: medium
impact: behavior
---
# BUG-169 — A dict key spelled like an index gets a wrong missing-field remedy

`_missing_field_error` spells its remedy by rewriting each `[N]` of the construction path as
`.N`, which was the maintainer's choice for BUG-165 over the exact fix
([construction](../../architecture/types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).
A dict key that literally contains `[N]` is rewritten too, so the remedy names a flag that
addresses a different key. Before BUG-165 this one case read correctly. The exact fix carries
the construction path as a tuple of segments (as pydantic does with its `loc`) and spells the
message and the flag from it. That touches every site that threads `path` through
construction, and the public `construct(path=...)` keyword. A key containing a dot is lossy in
the path string already: it reads the same as nesting.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Item:
    name: str
    size: int


@dataclass
class D:
    d: dict[str, Item]


try:
    confarg.load(D, argv=["--d.x[0].name", "a"], env={})
except Exception as e:
    print(type(e).__name__, e)
print(confarg.load(D, argv=["--d.x[0].name", "a", "--d.x[0].size", "1"], env={}))

# expected: the remedy names --d.x[0].size, the flag that sets key 'x[0]'
# actual:
#   MissingFieldError Missing required field 'd.x[0].size' of type <class 'int'>. Set it via CLI (--d.x.0.size), environment variable, or config file.
#   D(d={'x[0]': Item(name='a', size=1)})
```

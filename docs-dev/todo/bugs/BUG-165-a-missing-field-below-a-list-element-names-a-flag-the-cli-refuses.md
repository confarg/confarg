---
filed: 2026-10-05
where:
  - src/confarg/typedload/_construct.py::_missing_field_error
effort: S
risk: medium
impact: behavior
---
# BUG-165 — A missing field below a list element names a flag the CLI refuses

`_missing_field_error` builds its remedy as `--{path}`, but construction spells a sequence
element's path `items[0]` (`_build_items`, `_construct_tuple`) while the CLI spells it
`items.0`. So the error under a list or tuple element tells the user to pass `--items[0].size`,
which the CLI refuses as an unknown argument. The message is the one canonical "missing field"
text ([construction](../../architecture/types/construction.md#structs-collections-and-defaults)),
so the fix belongs there: spell the flag from the path's segments, each index as the CLI
spells it.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Item:
    name: str
    size: int


@dataclass
class Cfg:
    items: list[Item]


try:
    confarg.load(Cfg, argv=["--items.0.name", "a"], env={})
except Exception as e:
    print(type(e).__name__, e)
try:
    confarg.load(Cfg, argv=["--items[0].size", "1", "--items.0.name", "a"], env={})
except Exception as e:
    print(type(e).__name__, e)

# expected: the remedy names a flag the CLI accepts, --items.0.size
# actual:
#   MissingFieldError Missing required field 'items[0].size' of type <class 'int'>. Set it via CLI (--items[0].size), environment variable, or config file.
#   UnknownArgumentError Unknown argument: '--items[0].size' (field 'items[0].size' not found)
```

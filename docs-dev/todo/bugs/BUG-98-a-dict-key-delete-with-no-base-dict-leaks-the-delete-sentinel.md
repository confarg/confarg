# BUG-98 — A dict-key delete with no base dict errors on the leaked `_DeleteSentinel`

**Where:** `src/confarg/typedload/_construct.py` (the coercion path the surviving sentinel falls into) · **Filed:** 2026-09-30
**Effort:** S · **Risk:** low · **Impact:** behavior

A dict-key delete (`--d.k-`) is a patch, and a patch has nothing to bite on in an empty
document — the list delete says so in a purposeful message
(`_construct.py`: "requires a base list to delete from"), matching
[limitations.md#collections](../../architecture/limitations.md#collections). The dict-key
delete instead leaves its `_DeleteSentinel` in the merged dict when no base dict arrives from
any source, and the ordinary coercion path reports it as `Cannot coerce _DeleteSentinel
_DELETE_ to int at 'data.x'` — an internal leaked, naming a type the user never wrote. With a
base present (a config file), the delete works and an absent key is a silent no-op; only the
baseless spelling errors, and it errors wrong. Found while auditing delete semantics around
BUG-78.

Fix direction: detect the surviving sentinel where the list delete detects its baseless case
and raise the same style of purposeful error
([collection-patches.md](../../architecture/cli-parsing/collection-patches.md#collection-patch-operations)).

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class Config:
    data: dict[str, int] = field(default_factory=dict)


try:
    print(confarg.load(Config, argv=["--data.x-"], env={}))
except Exception as e:
    print(f"{type(e).__name__}: {e}")

# expected: an error that says a delete needs a base dict to apply to, as the
#           list delete's does ("requires a base list to delete from")
# actual:   TypeCoercionError: Cannot coerce _DeleteSentinel _DELETE_ to int at 'data.x'
```

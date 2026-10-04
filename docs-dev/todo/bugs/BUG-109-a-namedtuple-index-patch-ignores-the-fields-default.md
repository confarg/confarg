# BUG-109 — A namedtuple index patch ignores the field's default, where a tuple patch keeps it

**Where:** `src/confarg/typedload/_construct.py` (`_resolve_tuple_partial`) · **Filed:** 2026-10-01
**Effort:** S · **Risk:** medium · **Impact:** behavior

`--pair.1 5` on `pair: tuple[int, int] = (0, 0)` patches the default and builds `(0, 5)`.
The same patch on `pt: Pt = Pt(0, 0)` raises `MissingFieldError` for `pt.x`, on the CLI and in
the env channel alike. `_resolve_tuple_partial` lays an index-keyed dict over the field's
default, but it gates on `_is_tuple(ft)`, which a namedtuple does not pass. The canonical
"fixed arity, of which types?" question is `_types._fixed_seq_types`
([a namedtuple is a fixed-length sequence](../../architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence)).
Fix direction: gate on it, and accept name keys beside index keys when the field is a
namedtuple.

```python
from dataclasses import dataclass
from typing import NamedTuple
import confarg

class Pt(NamedTuple):
    x: int
    y: int

@dataclass
class Cfg:
    pair: tuple[int, int] = (0, 0)
    pt: Pt = Pt(0, 0)

print(confarg.load(Cfg, argv=["--pair.1", "5"], env={}))
try:
    print(confarg.load(Cfg, argv=["--pt.1", "5"], env={}))
except Exception as e:
    print(type(e).__name__, e)

# expected: Cfg(pair=(0, 5), ...) then Cfg(..., pt=Pt(x=0, y=5))
# actual:
#   Cfg(pair=(0, 5), pt=Pt(x=0, y=0))
#   MissingFieldError Missing required field 'pt.x' of type <class 'int'>. Set it via CLI (--pt.x), environment variable, or config file.
```

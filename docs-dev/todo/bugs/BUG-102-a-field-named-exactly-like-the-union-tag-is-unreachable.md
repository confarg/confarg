# BUG-102 — A field named exactly like the union tag is unreachable on every channel

**Where:** `src/confarg/_parse_cli.py` (`_resolve_field_type`, `_segment_names_real_field`) and
`src/confarg/typedload/_construct.py` (`_construct_struct_dispatch`) · **Filed:** 2026-10-01
**Effort:** L · **Risk:** high · **Impact:** config

A segment whose spelling equals `union_tag` exactly is the tag before anything asks whether a
real field bears that name: `_resolve_field_type` answers `str` at the tag check, and
`_construct_struct_dispatch` reads the key as the discriminator. A field named exactly like a
custom tag is therefore unreachable on every channel — its value is always imported as a
class path — while a field that differs only in case (`kind` under tag `Kind`) is a normal
field on the env channel (BUG-101, closed). The fix needs a precedence decision first — the
field wins, or the tag wins and the collision is refused loudly — which is the unsettled
tag counterpart of the casts rule in
[casts-and-reserved-words.md#real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins).

```python
from dataclasses import dataclass
import confarg


@dataclass
class Holder:
    Kind: str = "field"


print(confarg.load(Holder, argv=["--Kind", "v"], env={}, union_tag="Kind"))
# expected: Holder(Kind='v') — or a documented precedence that names the collision
# actual:   confarg.exceptions.TypeCoercionError: Cannot import class 'v' from 'Kind' tag
#           at '': Cannot import 'v': no importable module found in path. The value must
#           be a full dotted path, e.g. 'mypackage.mymodule.MyClass'.
```

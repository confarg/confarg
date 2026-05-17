# BUG-15 — `dump()` drops a leaf a union variant will steal back

**Where:** `src/confarg/_serialize.py` (`_serialize_union`) · **Filed:** 2026-09-13
**Effort:** L · **Risk:** medium · **Impact:** config

`load(dump(x)) != x`, the one round trip
[01-pipeline-and-contracts.md#public-api-seams](../../architecture/01-pipeline-and-contracts.md#public-api-seams)
does promise. Native file values are matched in declaration order, so any `Enum`, `Literal`,
registered leaf or type-ref variant ahead of the scalar steals the bare scalar on the way back
in; `Path | str` holding a plain `str` goes the same way. No `_Pinned` is involved — this is the
typed sibling of the pin `_serialize_untyped` now writes back
([05](../../architecture/05-types-and-construction.md#cast-pinning-in-files)), and unlike that
type-blind path the typed one knows the declared type and can decide. Fix direction: a
`_needs_cast` check on leaf variants mirroring `_needs_tag` on struct variants — emit `{__cast__, __value__}` only when re-reading the bare scalar would not
select the variant that produced it. Precedent: YAML emitters tag a scalar (`!!str 5`) exactly
when the plain form would resolve to another type. It changes `dump()` output, so it needs a
decision recorded in [10-design-decisions.md](../../architecture/10-design-decisions.md).
See [05-types-and-construction.md#serialization](../../architecture/05-types-and-construction.md#serialization).

```python
from dataclasses import dataclass
from enum import Enum
import confarg

class Color(Enum):
    FOO = 1

@dataclass
class Config:
    v: Color | str = Color.FOO

original = Config(v="FOO")
blob = confarg.dump(original)
print("dump  :", blob)
print("reload:", confarg.build(Config, blob))
# expected: dump  : {'v': {'__cast__': 'str', '__value__': 'FOO'}}
#           reload: Config(v='FOO')      — equal to `original`
# actual:   dump  : {'v': 'FOO'}
#           reload: Config(v=<Color.FOO: 1>)
```

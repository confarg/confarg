# BUG-31 — `dump()` crashes on a union with a subscripted or `Literal` variant

**Where:** `src/confarg/_serialize.py` (`_find_variant_type`) · **Filed:** 2026-09-17
**Effort:** M · **Risk:** medium · **Impact:** behavior

`_find_variant_type` picks the variant an instance belongs to with `isinstance(instance,
arg_r)`, which a parameterized generic (`list[str]`) and a `Literal` both refuse. Any union
holding one is therefore undumpable — `list[str] | str`, `dict[str, int] | str`,
`Literal["fast", "slow"] | str` — although every one of them loads fine. Fix direction: ask the
canonical shape functions instead of `isinstance` — `_types._is_seq_variant`,
`_is_dict`, `_fixed_seq_types` and `_is_literal` — the way `_construct_union_leaf` already
splits its buckets ([05-types-and-construction.md#union-construction](../../architecture/05-types-and-construction.md#union-construction)).
A `Literal` variant then also needs a serialized form: its members are plain scalars, so it
serializes as one ([05-types-and-construction.md#casting-a-stolen-leaf](../../architecture/05-types-and-construction.md#casting-a-stolen-leaf)
decides what happens when a sibling steals it back).

```python
from dataclasses import dataclass, field
import confarg

@dataclass
class Config:
    tags: list[str] | str = field(default_factory=list)

print(confarg.dump(Config(tags=["a"])))
# expected: {'tags': ['a']}
# actual:   TypeError: isinstance() argument 2 cannot be a parameterized generic
#           (Literal["fast", "slow"] | str raises "Subscripted generics cannot be used
#            with class and instance checks" the same way)
```

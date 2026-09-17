# BUG-32 — A `Literal` over `Enum` members refuses the value `dump()` writes

**Where:** `src/confarg/typedload/_coerce.py` (`_coerce_literal_value`) · **Filed:** 2026-09-17
**Effort:** M · **Risk:** high · **Impact:** behavior

`_match_literal_str_token` already ranks a `Literal`'s members by the type of their value, so
`--color red` builds `Color.RED` for `Literal[Color.RED]`
([05-types-and-construction.md#stealing-rule](../../architecture/05-types-and-construction.md#stealing-rule)).
The native-value branch beside it, `_coerce_literal_value`, compares against the members
themselves, so the same text out of a config file is refused — and that text is exactly what
`dump()` writes, since `_serialize_leaf` turns an `Enum` member into its value. A
`Literal`-over-`Enum` field therefore dumps to something `load()` cannot read, against
[10-design-decisions.md#dump-round-trips-at-the-built-object](../../architecture/10-design-decisions.md#dump-round-trips-at-the-built-object).
Fix direction: give the native branch the member matching the token branch already does, so
one rule answers for both channels.

```python
import enum
from dataclasses import dataclass
from typing import Literal

import confarg


class Color(enum.Enum):
    RED = "red"


@dataclass
class Config:
    color: Literal[Color.RED] = Color.RED


print(confarg.dump(Config()))
# {'color': 'red'}
print(confarg.build(Config, {"color": "red"}))
# expected: Config(color=<Color.RED: 'red'>)   (`--color red` on the CLI already builds it)
# actual:   TypeCoercionError: Cannot coerce str 'red' to Literal(<Color.RED: 'red'>,) at 'color'
```

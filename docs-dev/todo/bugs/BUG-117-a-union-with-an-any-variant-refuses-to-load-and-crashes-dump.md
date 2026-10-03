# BUG-117 — A union with an `Any` variant refuses to load and crashes `dump()`

**Where:** `src/confarg/_serialize.py` (`_variant_holds`), `src/confarg/typedload/_construct.py`
(`_construct_union`, `_construct_union_leaf`) · **Filed:** 2026-10-03
**Effort:** M · **Risk:** high · **Impact:** behavior

A bare `x: Any` field passes any value through, both ways. Put `Any` in a union and both
sides break. Construction refuses a value only `Any` accepts, because union dispatch never
offers it to the `Any` variant. Serialization crashes with a raw `TypeError` out of
`_variant_holds`, which reaches its class-check fallback with `typing.Any` itself: `Any` is a
class since Python 3.11, so the `isinstance(checkable, type)` guard lets it through, and
`isinstance(instance, Any)` raises. The comment there says "`Any` ... holds nothing in
particular", but the code never gets as far as answering. Found while closing REF-47: the
`_TypeKind.ANY` branch of `_variant_holds` still keeps the old fallback, so this behavior is
unchanged.

Fix direction: `Any` as a variant holds every instance and accepts every value, tried last so
that a more specific variant keeps what it can take (the stealing rule's order,
[stealing-rule.md](../../architecture/types/stealing-rule.md)). Or, if the maintainer would rather
not support it, refuse such a union with a clear error on both sides. A leaked `TypeError` is
wrong either way.

```python
from dataclasses import dataclass
from typing import Any

import confarg


@dataclass
class Config:
    x: list[int] | Any = None


try:
    print(confarg.from_dict(Config, {"x": 3}))
except Exception as e:
    print(f"{type(e).__name__}: {e}")
try:
    print(confarg.dump(Config(x=3)))
except Exception as e:
    print(f"{type(e).__name__}: {e}")

# expected: Config(x=3)
#           {'x': 3}
# actual:   TypeCoercionError: Cannot coerce int 3 to list | Any at 'x'
#           TypeError: typing.Any cannot be used with isinstance()
```

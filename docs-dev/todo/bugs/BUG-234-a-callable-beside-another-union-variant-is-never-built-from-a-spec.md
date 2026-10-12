---
filed: 2026-10-12
where:
  - src/confarg/typedload/_construct.py::_construct_union  # a class: spec is routed to the struct tags
  - src/confarg/typedload/_construct.py::_coerce_scalar_variants  # the Callable variant is tried as a scalar
effort: M
risk: medium
impact: behavior
severity: major  # a Callable field in such a union cannot be configured at all
needs_design: true  # which variant a dotted-path string selects in `Callable | str`
introduced_by: [PR-5]  # union construction never dispatched a callable spec
---
# BUG-234 — A Callable beside another union variant is never built from a spec

A Callable field resolves its spec ([spec grammar](../../architecture/callables.md#spec-grammar)), and so does `Callable | None`, whose one variant is built through `construct`. A union that pairs the Callable with any other non-None variant never does. `_construct_union_leaf` tries the Callable variant as a scalar leaf (`_construct_scalar`), which resolves no spec, so a dotted path loads as the `str` variant in `Callable | str` and is refused in `Callable | Opts`. A `{bind: …}` spec is refused in both, and a `{class: …}` spec is read as the struct union tag (`_construct_union_by_tag`), which a callable class does not match. `dump()` warns that such a value will not read back, which is true. The design question is precedence: in `Callable | str`, a string naming an importable function could be either.

Origin: the initial version dispatched a callable spec only from a field whose resolved type is a Callable, and built a union's leaf variants through `_construct_scalar`, which has no Callable branch. Latent since then. The `Callable | None` case works because a single-variant union builds its variant through `construct`.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


def double(x: int) -> int:
    return 2 * x


@dataclass
class Opts:
    level: int = 0


@dataclass
class WithStr:
    f: Callable[[int], int] | str


@dataclass
class WithStruct:
    f: Callable[[int], int] | Opts


print(repr(confarg.from_dict(WithStr, {"f": "__main__.double"}).f))
# expected: <function double at 0x...>
# actual:   '__main__.double'
print(confarg.from_dict(WithStruct, {"f": "__main__.double"}).f)
# expected: <function double at 0x...>
# actual:   confarg.exceptions.TypeCoercionError: Cannot coerce str '__main__.double' to Callable | Opts at 'f'
```

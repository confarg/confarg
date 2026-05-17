# BUG-57 — `_StrToken` leaks into the Callable `bind` error message

**Where:** `src/confarg/_callable.py` (`_resolve_dict_spec`, the `bind_raw` check) ·
**Filed:** 2026-09-29
**Effort:** S · **Risk:** low · **Impact:** behavior

A `bind:` value that is not a mapping is rejected with `type(bind_raw).__name__`, which prints
the private `_StrToken` wrapper whenever the value came from the CLI or the environment. Tokens
never reaching a message is an invariant
([09-invariants.md#tokens-mean-untyped-text](../../architecture/09-invariants.md#tokens-mean-untyped-text)),
argued in
[05-types-and-construction.md#token-model](../../architecture/05-types-and-construction.md#token-model).

The same defect in `typedload/_construct.py` was BUG-40, closed by routing its four sites
through `_coerce._src_type`. This fifth site is in another module and was named by neither
BUG-40 nor REF-51, so it survived. `_callable.py` already imports from `confarg._types`, so the
fix is the same one line — but `_src_type` lives in `typedload/_coerce.py`, and importing
`typedload` from `_callable` is the wrong direction for the source map
([README § Source map](../../architecture/README.md)): move `_src_type` down beside `_StrToken`
in `_types.py` first, which also makes it reachable from the other channels.

```python
from dataclasses import dataclass
from typing import Any, Callable

import confarg


def target(a: int = 1) -> int:
    return a


@dataclass
class Cfg:
    fn: Callable[..., Any] = target


confarg.load(Cfg, argv=["--fn.fn", "__main__.target", "--fn.bind", "notadict"], env={})

# expected: TypeCoercionError: 'bind' in Callable dict at 'fn' must be a dict, got str
# actual:   TypeCoercionError: 'bind' in Callable dict at 'fn' must be a dict, got _StrToken
```

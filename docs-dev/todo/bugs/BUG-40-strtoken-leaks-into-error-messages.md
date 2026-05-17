# BUG-40 — `_StrToken` leaks into user-facing error messages

**Where:** `src/confarg/typedload/_construct.py` (four `type(data).__name__` sites) ·
**Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** behavior

Four error paths name the value's type with `type(data).__name__`, which prints the private
`_StrToken` wrapper. Two neighbouring paths in the same module use the purpose-built
`_coerce._src_type` and print `str`. Tokens never reaching a message is an invariant
([09-invariants.md#tokens-mean-untyped-text](../../architecture/09-invariants.md#tokens-mean-untyped-text)),
argued in [05-types-and-construction.md#token-model](../../architecture/05-types-and-construction.md#token-model).

Fix direction: route all six through `_src_type`. It is the same one-line decision made twice,
so the durable fix is the shared error builder in
[REF-51](../refactors/REF-51-error-messages-outside-the-factories.md) rather than four edits.

```python
from dataclasses import dataclass, field
import confarg


@dataclass
class Cfg:
    xs: list[int] = field(default_factory=list)


confarg.load(Cfg, argv=[], env={"P_XS": "abc"}, env_prefix="P_")

# expected: TypeCoercionError: Cannot construct list at 'xs':
#           expected list or dict with integer keys, got str 'abc'
# actual:   TypeCoercionError: Cannot construct list at 'xs':
#           expected list or dict with integer keys, got _StrToken 'abc'
```

# BUG-41 — A class nested inside a class does not round-trip its union tag

**Where:** `src/confarg/_serialize.py` (two `f"{tp.__module__}.{tp.__name__}"` sites) ·
**Filed:** 2026-09-24
**Effort:** S · **Risk:** medium · **Impact:** config

Serialization writes the tag as `__module__` + `__name__`; the reader resolves it as a dotted
import path, which for a nested class needs `__qualname__`. `_construct.py` and `_callable.py`
use `__qualname__` and are right. So `dump()` emits a tag its own `from_dict()` cannot read, and
the configuration it wrote is unloadable — the round trip that
[01-pipeline-and-contracts.md#public-api-seams](../../architecture/01-pipeline-and-contracts.md#public-api-seams)
promises.

A class nested in a *function* happens to survive, because the tag is then matched against
`__subclasses__()` rather than imported; only the module-attribute lookup fails. That is why the
reproduction nests the class in a class.

Fix direction: the dotted name is spelled at twelve sites in two spellings. Give it one owner —
see [REF-51](../refactors/REF-51-error-messages-outside-the-factories.md), which is the fix that
stops the next recurrence; fixing the two `_serialize.py` sites alone leaves the divergence in
place. `_serialize._serialize_leaf` is already the canonical "how a leaf value leaves the
library" ([09-invariants.md](../../architecture/09-invariants.md)); the class tag deserves the
same treatment.

```python
from dataclasses import dataclass, field
import confarg


@dataclass
class Base:
    a: int = 0


class Outer:
    @dataclass
    class Sub2(Base):
        b: int = 2


@dataclass
class Holder:
    s: Base = field(default_factory=Base)


dumped = confarg.dump(Holder(s=Outer.Sub2()))
print(dumped)
print(confarg.from_dict(Holder, dumped))

# expected: {'s': {'a': 0, 'b': 2, 'class': '__main__.Outer.Sub2'}}
#           Holder(s=Outer.Sub2(a=0, b=2))
# actual:   {'s': {'a': 0, 'b': 2, 'class': '__main__.Sub2'}}
#           confarg.exceptions.TypeCoercionError: Cannot import class '__main__.Sub2' from
#           'class' tag at 's': Cannot import '__main__.Sub2': module '__main__' has no
#           attribute 'Sub2'. The value must be a full dotted path, e.g.
#           'mypackage.mymodule.MyClass'.
```

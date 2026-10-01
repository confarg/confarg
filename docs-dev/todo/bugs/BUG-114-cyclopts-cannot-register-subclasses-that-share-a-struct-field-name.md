# BUG-114 — Cyclopts cannot register subclasses that share a struct field name

**Where:** `src/confarg/cli/cyclopts/_register.py` (group creation per struct field) ·
**Filed:** 2026-10-01
**Effort:** S · **Risk:** medium · **Impact:** behavior

When two subclasses of a field's base type each declare a struct field with the same name and
different types, `populate_app` gives cyclopts two distinct `Group` objects with one name.
Cyclopts raises at its first parse, even with an empty argv, so the target cannot be used with
cyclopts at all. The other front-ends register it (but see BUG-113). Not bisected: it may
predate the recent inheritance-walk fixes *(inferred)*. Fix direction: reuse one `Group` per
group name *(inferred — the registration code has not been read for the cause)*.

```python
from dataclasses import dataclass, field

import cyclopts

from confarg.cli.cyclopts import populate_app


@dataclass
class A:
    a: int = 0


@dataclass
class B:
    b: int = 0


@dataclass
class Base:
    pass


@dataclass
class S1(Base):
    inner: A = field(default_factory=A)


@dataclass
class S2(Base):
    inner: B = field(default_factory=B)


@dataclass
class Cfg:
    item: Base = field(default_factory=Base)


app = cyclopts.App()
populate_app(Cfg, app, argv=[])
app.parse_args([])
print("parsed")

# expected:
#   parsed
# actual:
#   ValueError: Cannot register 2 distinct Group objects with same name.
```

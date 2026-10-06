---
filed: 2026-10-01
where:
  - src/confarg/cli/cyclopts/_register.py::_spec_to_inspect_param  # one new Group per spec
effort: S
risk: medium
impact: behavior
severity: major  # the target cannot be used with cyclopts at all
introduced_by: [PR-38]  # fix: Fix inheritance-based dispatch in CLI integrations
---
# BUG-114 — Cyclopts cannot register subclasses that share a struct field name

When two subclasses of a field's base type each declare a struct field with the same name and
different types, `populate_app` gives cyclopts two distinct `Group` objects with one name.
Cyclopts raises at its first parse, even with an empty argv, so the target cannot be used with
cyclopts at all. The other front-ends register it (but see BUG-113). `_spec_to_inspect_param`
builds a new `Group` for every spec, from its `group` and `group_description`: here the specs
`item.inner.a` and `item.inner.b` both carry the group `item.inner`, described as
`A(a: int = 0)` and `B(b: int = 0)`. Fix direction: one `Group` per group name.

Origin: regression from PR-38, a bug fix that made the CLI adapters register the fields of a base
type's subclasses. Bisected with the reproduction: PR-37 parses, PR-38 raises. BUG-113 comes from
the same revision: registering each subclass's fields on its own is also what lets the adapters
accept a path vanilla refuses.

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

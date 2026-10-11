---
filed: 2026-10-07
where:
  - src/confarg/_merge.py::_deep_merge
  - src/confarg/_merge.py::_open_for_ops
  - src/confarg/typedload/_construct.py::_is_typed_call
effort: M
risk: medium
impact: behavior
severity: critical  # the struct case loads a wrong value silently; the list case fails loudly
needs_design: true  # the merge is untyped, and a `call` key is a spec on one field and data on another
introduced_by: [FEAT-28]
---
# BUG-190 — A typed `call:` spec merges with the lower layer's value instead of replacing it

A `call:` spec on a field that is no Callable is a fresh value, but the merge treats it as a
patch of whatever a lower layer set there. On a struct field, the lower layer's keys become
arguments of the call. When the function takes them, the result is wrong and nothing reports it.
On a list field, the lower layer's list arrives as the merge's own `'*'` key, and the call
refuses it as an unknown argument. A union tag already replaces the value below it for the same
reason ([a class tag replaces](../../architecture/design-decisions/class-tag-replaces.md)). The
merge cannot apply that rule to `call` by key alone, though: a dict field and a struct with a
member named `call` hold the key as data
([call yields to data](../../architecture/design-decisions/call-yields-to-the-data-a-type-holds.md)).
So the fix is a design question first. One option is to let `build()` drop the base under a
typed call, since it is the first step that knows the type.

Origin: FEAT-28 made `call:` a spec on every typed field
([call in a typed field](../../architecture/callables.md#call-in-a-typed-field)), but did not
change the merge, which kept reading the key as data. Before it, the reproduction fails with
`Unknown field(s) ['call'] for Point`. It is a regression of a feature that has just landed, not
latent.

```python
import pathlib
import tempfile
from dataclasses import dataclass, field

import confarg


@dataclass
class Point:
    a: int = 0
    b: int = 0


def square(a: int = 1) -> Point:
    return Point(a, a)


def pair(a: int) -> list[int]:
    return [a, a]


@dataclass
class Config:
    p: Point = field(default_factory=Point)
    xs: list[int] = field(default_factory=list)


d = pathlib.Path(tempfile.mkdtemp())
(d / "base.yaml").write_text("p: {a: 5}\nxs: [1, 2]\n")
(d / "over.yaml").write_text("p: {call: __main__.square}\n")
cfg = confarg.load(Config, argv=[], env={}, files=[d / "base.yaml", d / "over.yaml"])
print(cfg.p)  # expected: Point(a=1, b=1); actual: Point(a=5, b=5)

(d / "over.yaml").write_text("xs: {call: __main__.pair, a: 3}\n")
confarg.load(Config, argv=[], env={}, files=[d / "base.yaml", d / "over.yaml"])  # expected: xs == [3, 3]
```

Actual output, from the parent revision of the one that filed this (`uvlzknnu`), run as
`repro_call_layers.py`:

```text
Point(a=5, b=5)
confarg.exceptions.TypeCoercionError: Unknown kwargs ['*'] for 'pair' at 'xs'. Valid parameters: ['a'].
```

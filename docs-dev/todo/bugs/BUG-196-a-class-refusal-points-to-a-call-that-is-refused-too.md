---
filed: 2026-10-07
where:
  - src/confarg/exceptions.py::TypeCoercionError
  - docs-dev/architecture/design-decisions/class-names-a-subclass-call-computes.md
effort: S
risk: low
impact: behavior
severity: minor  # a misleading remedy in an error message; the refusal itself is right
introduced_by: [FEAT-29]  # TypeCoercionError.tag_not_a_subclass and its decision note
---
# BUG-196 — A class refusal on a typed field points to a `call:` that is refused too

`class:` on a typed field naming a class that is no subclass of the annotation is refused, and
`TypeCoercionError.tag_not_a_subclass` tells the user to build that class with a factory in a
`call:` spec instead. Doing so fails: a typed `call:` takes its result only when the annotation
accepts it, and builds anything else as the annotation, so an `Other` returned for a `Base` field
is refused in turn ([call in a typed field](../../architecture/callables.md#call-in-a-typed-field)).
The decision note promises the same remedy in its *Cost* line, against its own reason for the
refusal: the annotation is the contract the rest of the program reads. The fix is in the message
and the note: a `call:` computes a value the annotation accepts, it does not get around it.

Origin: FEAT-29 added the refusal and pointed it to `call:`, the form the redesign gave "compute
the value". FEAT-28, one revision earlier, had already made a typed `call:` check its result
against the annotation, and FEAT-29 read `call:` as an escape from that check. Latent since
FEAT-29.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Base:
    x: int = 0


@dataclass
class Other:
    x: int = 0


def make_other(x: int) -> Other:
    return Other(x)


@dataclass
class Config:
    b: Base


for spec in ({"class": "__main__.Other"}, {"call": "__main__.make_other", "x": 1}):
    try:
        print(confarg.build(Config, {"b": spec}))
    except confarg.exceptions.ConfargError as e:
        print(f"{type(e).__name__}: {e}")
# expected: the first refusal names a remedy that works, or none
# actual:
# TypeCoercionError: Class '__main__.Other' at 'b' is not a subclass of __main__.Base. To build
#     __main__.Other with a factory, give the field a 'call:' spec instead.
# TypeCoercionError: Cannot construct Base at 'b': expected dict, got Other Other(x=1)
```

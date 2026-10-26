---
filed: 2026-10-26
where:
  - src/confarg/_callable.py::_accepts
  - src/confarg/_callable.py::resolve_typed_call
effort: M  # which results construction re-reads, and which it takes as built
needs_design: true  # a struct instance is taken as it is; a container's items and a fixed length are not checked today
risk: high  # construction is shared by every channel, and a wrong acceptance is silent in all of them
impact: config  # a call returning items its field does not hold starts failing, or starts coercing them
severity: critical  # the value is left uncoerced and unchecked, with no error
introduced_by: [FEAT-28]  # _accepts, which answers by the outer class only
---

# BUG-293 — A `call:` result is taken unchecked when its outer class matches

On a typed field, "a value the annotation already accepts is taken as it is; any other is built as the annotation, so a wrong type fails the way a wrong literal does" ([call in a typed field](../../architecture/callables.md#call-in-a-typed-field)).
`_callable._accepts` answers "accepts" by `isinstance` against the annotation's origin alone, so `tuple[int, int]` takes a three-item tuple and `list[int]` a list of strings, neither coerced nor refused.
It also disagrees with `_serialize._holds`, the dump's answer to the same question: `_accepts(tuple[int, int], (1, 2, 3))` is `True` where `_holds` is `False`, and `_accepts(Literal[1], 1)` and `_accepts(float, 1)` are `False` where `_holds` is `True`.

Fix direction, for the design pass: take a result as it is only when it is an instance of the struct the annotation names, and build every other through construction, which already reads a native container and coerces or refuses its items; then decide whether `_accepts` and `_holds` become one predicate.
FEAT-57 waits for this ticket, so that it writes its Protocol branch once, in whatever predicate this one leaves ([the Protocol plan](../plans/protocol-typed-fields.md#phases)).

Origin: latent since FEAT-28, which dispatched `call:` on every typed field and added `_accepts` to skip constructing a value that already has the annotation's type; it tested the origin class, enough for the structs and scalars it was written for, not for a parameterized container.

```python
from dataclasses import dataclass

import confarg


def three():
    return (1, 2, 3)


def letters():
    return ["a", "b"]


@dataclass
class C:
    t: tuple[int, int]
    xs: list[int]


print(confarg.build(C, {"t": {"call": "__main__.three"}, "xs": {"call": "__main__.letters"}}))

# expected: TypeCoercionError at 't' (3 items for 2 positions) and at 'xs.0' ('a' is no int)
# actual:   C(t=(1, 2, 3), xs=['a', 'b'])
```

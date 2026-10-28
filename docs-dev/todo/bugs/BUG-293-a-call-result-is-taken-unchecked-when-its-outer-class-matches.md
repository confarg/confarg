---
filed: 2026-10-26
where:
  - src/confarg/_callable.py::_accepts  # deleted
  - src/confarg/_callable.py::resolve_typed_call
  - src/confarg/_serialize.py::_holds  # moved, with its helpers, to a new typedload/_holding.py
  - src/confarg/_serialize.py::_variant_holds
  - src/confarg/_serialize.py::_holds_members
  - src/confarg/typedload/_construct.py::_holds_anything
  - src/confarg/typedload/_construct.py::_construct_struct_dispatch  # takes a built instance _holds holds
  - src/confarg/typedload/_construct.py::_construct_union  # routes a built instance to the variant holding it
  - src/confarg/typedload/_coerce.py::_coerce_leaf  # an unsupported leaf takes an instance of its class
  - src/confarg/exceptions.py::TypeCoercionError  # the refusal of an instance its node does not hold
effort: L  # crosses every channel and records a decision
risk: high  # construction is shared by every channel, and a wrong acceptance is silent in all of them
impact: config  # a call returning items its field does not hold starts failing, or starts coercing them
severity: critical  # the value is left uncoerced and unchecked, with no error
introduced_by: [FEAT-28]  # _accepts, which answers by the outer class only
blocked_by: [FEAT-60]  # a tuple under Sequence[int] keeps building
---

# BUG-293 — A `call:` result is taken unchecked when its outer class matches

On a typed field, "a value the annotation already accepts is taken as it is; any other is built as the annotation, so a wrong type fails the way a wrong literal does" ([call in a typed field](../../architecture/callables.md#call-in-a-typed-field)).
`_callable._accepts` answers "accepts" by `isinstance` against the annotation's origin alone, so `tuple[int, int]` takes a three-item tuple and `list[int]` a list of strings, neither coerced nor refused.
It also disagrees with `_serialize._holds`, the dump's answer to the same question: `_accepts(tuple[int, int], (1, 2, 3))` is `True` where `_holds` is `False`, and `_accepts(Literal[1], 1)` and `_accepts(float, 1)` are `False` where `_holds` is `True`.

Settled in [the plan](../plans/a-calls-value-is-read-by-construction.md): `_accepts` is deleted and every value a `call:` computes goes through construction, which reads it as it reads `build()` data; construction takes a built instance of what its node names as it is — a struct by `_holds`, the dump's predicate, moved where construction can ask it, so a generic struct's members are checked; an unsupported leaf by `isinstance` — in a caller's `build()` data too.
So `_accepts` and `_holds` become one predicate, and FEAT-57 writes its Protocol branch in it ([the Protocol plan](../plans/protocol-typed-fields.md#phases)).

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

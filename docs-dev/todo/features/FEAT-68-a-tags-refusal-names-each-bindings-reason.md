---
filed: 2026-11-12
where:
  - src/confarg/typedload/_construct.py::_construct_bound_tag  # the last binding refuses as itself
  - src/confarg/exceptions.py::_variant_reason  # the reasons a union's refusal gives, one per variant
effort: M  # the format exists; the work is a refusal per binding and its tests
risk: medium  # a message only, but the bindings' refusals mix paths and kinds
impact: behavior  # an error message names every binding's reason
severity: minor  # a loud refusal that names one binding of several
---

# FEAT-68 — A tag's refusal names each binding's reason

A tag naming a class that several variants bind apart, `Box[float] | Box[int]` with `{class: Box, item: true}`, tries each binding in declaration order and, when none builds, raises the last binding's refusal alone: `Cannot coerce bool True to int at 'u.item'`.
`Box[float]`'s refusal is dropped, so the message names a type the user may not have meant the field to have, and says nothing of the binding tried first.
BUG-300, once it lands, extends the walk to bindings of two classes (`Both` under `Src[float] | Snk[int]`), where the class the message names is not one the field declares.

A union's own refusal already names each variant's reason on a line of its own ([a union refusal names each variant's reason](../../architecture/types/construction.md#a-union-refusal-names-each-variants-reason), FEAT-46, read by `exceptions._variant_reason`); the bindings' walk (`_construct._construct_bound_tag`, through `_first_that_builds`) collects the refusals and drops all but the last.
The refusal could keep that format, naming each binding by `_types._spell_type`:

```text
Cannot build Box at 'u' from its class key:
  Box[float]: cannot coerce bool True to float at 'u.item'
  Box[int]: cannot coerce bool True to int at 'u.item'
```

A lone binding keeps refusing as itself, and the exception type the bindings raise has to be settled when they differ (a `MissingFieldError` from one, a `TypeCoercionError` from another).

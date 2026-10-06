---
filed: 2026-10-06
where:
  - src/confarg/_callable.py
  - src/confarg/typedload/_construct.py
effort: S
risk: low
impact: api
severity: minor
---
# FEAT-29 — `class:` only names classes compatible with the target type

`class:` on a typed field must name a subclass of the field's annotation, as the struct
construction already requires. A class that is not compatible raises, and the message points to
`call:`. Under a `Callable` annotation, `class:` keeps its current meaning: the instance must be
callable.

`call:` remains able to build the same class. That is deliberate: `class:` says "the type I
want", and `call:` says "compute it". Confirm the current behavior of `class:` on a plain typed
field before changing it: this ticket assumes it is only meaningful under `Callable`, and that
needs checking in the code, not from memory.

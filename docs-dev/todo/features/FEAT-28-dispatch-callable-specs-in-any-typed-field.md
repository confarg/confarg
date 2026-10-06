---
filed: 2026-10-06
where:
  - src/confarg/typedload/_construct.py
  - src/confarg/_callable.py
effort: L
risk: medium
impact: behavior
severity: minor
---
# FEAT-28 — Dispatch `call:` and `class:` specs in every typed field

Callable spec dicts are dispatched only for `Callable`-annotated fields
(`typedload/_construct.py`, the `_resolve_callable_spec` branch). Move dispatch into the general
constructor so `call:` works for an `int`, a dataclass, or any other annotation. The result is
checked against the annotation through the existing typed construction, so a wrong type fails
the same way a wrong literal does.

Additive: `fn:`, `bind:` and existing `call:` on `Callable` fields keep working.
Foundation for FEAT-29 to FEAT-31 and FEAT-33.

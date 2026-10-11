---
filed: 2026-10-06
where:
  - src/confarg/_serialize.py
  - src/confarg/_callable.py
effort: M
risk: low
impact: behavior
severity: minor
---
# FEAT-33 — Dump of resolved values produced by `call:`

A resolved value from `call:` keeps its spec only when the value can carry an attribute
(`__confarg_spec__`, stamped by `_resolve_class_spec` today). Computed values such as `int`, `str`
or a plain tuple lose it, so `dump()` of a resolved config writes the value, not the spec. This
is the boundary we agreed on: unresolved merged configs dump as written; resolved computed values
dump as values.

Work: extend the stamping to `call:` results that can carry it, keep the `_serialize_untyped`
path unchanged for the unresolved tree, and assert both in tests. Document the boundary in the
architecture note when FEAT-34 lands.

---
filed: 2026-09-12
where:
  - src/confarg/_callable.py
effort: L
risk: medium
impact: behavior
severity: minor
---

# FEAT-2 — Protocol-typed callables and `**kwargs`

Callable specs bind against a concrete signature.
A field typed as a `Protocol` with `__call__`, or a target accepting `**kwargs`, has no story yet: decide whether extra keys bind as keyword arguments and how they are validated.
See [callables.md](../../architecture/callables.md).

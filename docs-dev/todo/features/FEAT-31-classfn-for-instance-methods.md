---
filed: 2026-10-06
where:
  - src/confarg/_callable.py
effort: L
risk: medium
impact: config
severity: major
blocked_by: [FEAT-28]
---
# FEAT-31 — `classfn:` names an instance method and takes the owner's constructor arguments

`{classfn: C.m, <init>}` builds `C(**init)` and returns its bound method `m`. Siblings of
`classfn` are constructor arguments. Under `call:` or `bind:`, siblings of the directive are
arguments of the method, so the two namespaces never meet.

`classmethod` and `staticmethod` targets need no owner. A plain path works (`call: C.cm`,
`bind: C.sm`), and `classfn:` is not needed for them. The bare-path case for an instance method
(auto-instantiation versus error) is open in FEAT-27 and decided here, with the default kept.

Replaces today's `fn: C.m` with siblings, which currently builds the owner the same way.

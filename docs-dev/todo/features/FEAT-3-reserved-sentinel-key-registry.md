---
filed: 2026-09-12
effort: S
risk: high
impact: config
needs_design: true  # the effort sizes the design pass; the implementation is not sized
---
# FEAT-3 — A registry of reserved sentinel keys

`__root__`, `__cast__`, `__value__`, `__include__`, `+`, `-`, `*`, `~` are recognised in
several places. One registry, plus a guard against user keys colliding with them, would harden
the plain-dict IR. See [pipeline/deep-merge.md#deep-merge-semantics](../../architecture/pipeline/deep-merge.md#deep-merge-semantics).

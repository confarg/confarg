---
filed: 2026-09-12
effort: S
risk: low
impact: behavior
needs_design: true  # the effort sizes the design pass; the implementation is not sized
---
# FEAT-5 — Optional structural validation right after `merge()`

Errors would surface earlier and closer to their source, without changing the
merge/build contract (`merge()` stays unvalidated by default).
See [pipeline/merge-build-contract.md#merge-build-contract](../../architecture/pipeline/merge-build-contract.md#merge-build-contract).

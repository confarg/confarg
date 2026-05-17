---
filed: 2026-09-12
effort: M
risk: high
impact: behavior
severity: minor
needs_design: true  # the effort sizes the design pass; the implementation is not sized
---

# FEAT-8 — Value provenance

Remember which source set each value (as Dynaconf's `inspect` does), as an opt-in richer IR.
Useful for `--help`-time explanations and for debugging precedence surprises.

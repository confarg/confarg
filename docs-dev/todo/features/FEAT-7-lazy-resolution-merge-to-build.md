---
filed: 2026-09-12
effort: M
risk: high
impact: behavior
needs_design: true  # the effort sizes the design pass; the implementation is not sized
---
# FEAT-7 — Lazy resolution between `merge` and `build`

For very large configurations, resolve only the branches actually constructed.

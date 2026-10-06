---
filed: 2026-10-06
where:
  - docs-dev/architecture/callables.md
effort: S
risk: low
impact: none
severity: trivial
blocked_by: [FEAT-30, FEAT-31, FEAT-32]
---
# FEAT-34 — Rewrite the callables architecture note and write the migration table

Once FEAT-30 to FEAT-32 land, `docs-dev/architecture/callables.md` describes the new grammar
(`bind`, `call`, `class`, `classfn`), the rules for siblings, the decisions in FEAT-27 and FEAT-29,
and the dump boundary from FEAT-33. The old-to-new migration table from FEAT-30 goes in the user
documentation, not here.

Rationale stays in the architecture note; this ticket is closed by the rewrite, not by a copy of
the design text left on the board.

---
filed: 2026-10-06
where:
  - docs-dev/architecture/callables.md
effort: S
risk: low
impact: none
severity: trivial
blocked_by: [FEAT-31, FEAT-32]
---
# FEAT-34 — Rewrite the callables architecture note and write the migration table

Once FEAT-31 and FEAT-32 land, `docs-dev/architecture/callables.md` describes the new grammar
(`bind`, `call`, `class`, `classfn`), the rules for siblings, the decisions in FEAT-27 and the `class:` decision already recorded,
and the dump boundary from FEAT-33. The old-to-new migration table goes in the user
documentation, not here:

| Old | New |
|---|---|
| `f: {fn: pkg.g, bind: {a: 1}}` | `f: {bind: pkg.g, a: 1}` |
| `f: {fn: pkg.Cls, bind: {a: 1}}` (factory) | `f: {bind: pkg.Cls, a: 1}` |
| `f: {class: pkg.H, x: 1, bind: {p: 2}}` | `f: {bind: {class: pkg.H, x: 1}, p: 2}` |
| `f: {fn: pkg.C.m, x: 1}` | `f: {classfn: pkg.C.m, x: 1}` (FEAT-31) |
| `f: {class: pkg.Cls, x: 1}` | `f: {class: pkg.Cls, x: 1}` (unchanged) |
| `f: {call: pkg.g, a: 1}` | `f: {call: pkg.g, a: 1}` (unchanged) |

FEAT-30 already brought `callables.md` in line with the grammar it landed; what is left is
`classfn` and the FEAT-33 boundary.

Rationale stays in the architecture note; this ticket is closed by the rewrite, not by a copy of
the design text left on the board.

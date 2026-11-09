---
filed: 2026-11-09
where:
  - README.md
  - docs/index.md
effort: S
risk: low  # prose only; BUG-322's reproduction keeps the examples honest
impact: none
severity: minor  # a reader cannot tell what confarg offers that jsonargparse does not
---

# FEAT-64 — The README says who confarg is for, and why not jsonargparse

The README and the landing page list features — unions, inheritance, expressions, composition, CLI integration — without saying who needs them, or what confarg does that the closest alternative does not.
jsonargparse covers most of the same ground ([comparison](../../../docs/comparison.md#jsonargparse)), so a reader who knows it has no reason to read further.

The headline, the target user and the "why not jsonargparse" paragraph are decided in [the value-proposition plan](../plans/value-proposition.md#decisions); the README opens with them and links the comparison page.
Precedents: tyro's "Goals and alternatives" page and typed-settings' "Why Typed Settings" page each answer "why not X" by name.

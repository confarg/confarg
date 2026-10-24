---
filed: 2026-10-20
where:
  - src/confarg/_depth.py::_shortened
  - src/confarg/exceptions.py::_spell_long_path
  - src/confarg/dictexpr/_expressions.py  # _MAX_DEPTH
effort: S
risk: low
impact: none
severity: trivial
---

# REF-117 — Two depth bounds share a name, and two rules elide a long path

- `_depth.MAX_DEPTH = 64` bounds how deep a configuration nests; `dictexpr._expressions._MAX_DEPTH = 100` bounds how deep an expression's syntax tree nests (BUG-145).
  Different quantities, one name: a reader meeting `_MAX_DEPTH` in the engine is one import away from the wrong one.
  `_MAX_EXPRESSION_DEPTH` would say which.
- A refusal elides a long path twice over: `exceptions._spell_long_path` keeps the first three and last two segments past eight, `_depth._shortened` keeps the first 24 and last 12 characters of a flag past 40, and its docstring says it does so "as a path is".
  The flag is its path spelled with dots, so one rule — by segments — would serve both.

See [a-configuration-nests-at-most-64-levels.md](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#a-configuration-nests-at-most-64-levels).

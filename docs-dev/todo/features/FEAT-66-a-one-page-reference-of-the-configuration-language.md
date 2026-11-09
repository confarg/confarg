---
filed: 2026-11-09
where:
  - zensical.toml  # plus a new page under docs/
  - docs/reference.md
effort: M
risk: low
impact: none
severity: minor  # a user learns a reserved key or an expression rule from the error it raises
---

# FEAT-66 — A one-page reference of the configuration language

What a configuration file, a flag or a variable can spell is spread over twenty-four tutorials, and no page lists it: the reserved keys (`__include__`, `__cast__`, `__value__`, `__root__`, `__unset__`, `__append__`, `__delete__`, `__delete_after__`, `__base__`), the list and key ops (`+`, `-`, an index), the casts (`.json`, `.int`), the openers (`class`, `classfn`, `bind`, `call`, `args`), `locals` and `_locals`, and the expression forms (`${a.b}`, `${.b}`, `${::b}`, subscripts, the whitelist).
`docs/reference.md` documents the Python API only.

One page, each form with a line of explanation, a one-line example and a link to the tutorial that teaches it.
[FEAT-26](FEAT-26-the-expression-whitelist-is-not-documented-for-users.md), the expression whitelist, becomes its expressions section.
The maintainer-facing material is in [reserved keys](../../architecture/config-files/reserved-keys.md#reserved-file-only-keys) and [the safety model](../../architecture/expressions/safety-model.md#safety-model).
See [the value-proposition plan](../plans/value-proposition.md#decisions).

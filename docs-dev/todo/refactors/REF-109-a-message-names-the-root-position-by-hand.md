---
filed: 2026-10-20
where:
  - src/confarg/_serialize.py
  - src/confarg/_files.py::_writable
  - src/confarg/typedload/_construct.py
  - src/confarg/exceptions.py::_spell_field_path
effort: S
risk: low
impact: none
severity: trivial
---

# REF-109 — A message names the root position by hand eleven times

"How does a message name a construction path?" is `exceptions._spell_field_path` in the [canonical table](../../architecture/invariants.md#delegate-to-the-canonical-function), but it spells the root as the empty string, so the refusals that must say *where* write `_spell_field_path(path) or _defaults.ROOT_KEY` at each call: eleven times across `_serialize`, `_files._writable` (twice per key, inside its loop) and `_construct`.
The sibling of [REF-97](REF-97-how-a-message-names-a-type-is-spelled-by-hand.md), for a position instead of a type.

Fix direction: one `_spelled_where(path)` beside `_spell_field_path`, taking the root's spelling as a parameter since `exceptions.py` imports nothing from confarg, or the message factories taking the path and spelling it themselves.

---
filed: 2026-10-20
where:
  - src/confarg/_types.py::_fixed_position
  - src/confarg/_parse_cli.py::_namedtuple_index_spellings
  - src/confarg/_parse_cli.py::_step_tuple_type
  - src/confarg/_parse_cli.py::_advance_field_type
  - src/confarg/_default_layer.py::_element_type
  - src/confarg/_default_layer.py::_lay_unset_positions
  - src/confarg/_merge.py::_unset_positions
  - docs-dev/architecture/invariants.md
effort: M
risk: low
impact: none
severity: trivial
---

# REF-105 — A fixed-length position is read and spelled by hand around `_fixed_position`

Q-1 made `_types._fixed_position` the one reader of a fixed tuple's and a namedtuple's position, and the code around it still spells the rest of the subject per site:

- **Which index spellings exist** has two sources.
  `_parse_cli._namedtuple_index_spellings` is documented as "the one source" (BUG-97) and feeds registration through `_namedtuple_position_spellings`; `_fixed_position` re-derives the same `-n..n-1` range on its own, and the [canonical table](../../architecture/invariants.md#delegate-to-the-canonical-function) lists both.
  One should be defined by the other.
- **The key a position is written under**, the inverse of `_fixed_position`, is spelled twice: `_merge._unset_positions` (`names[i] if i < len(names) else str(i)`) and `_default_layer._lay_unset_positions` (`names[i] if names else str(i)`).
- **The type at a key** is spelled three times: `_default_layer._element_type` (`_fixed_seq_types` then `_fixed_position`), `_parse_cli._step_tuple_type` (`_tuple_types` then `_fixed_position`) and `_advance_field_type`'s namedtuple branch (`list(_namedtuple_fields(tp).values())[position]`).

Fix direction: `_types` grows `_position_key(tp, i)` and `_position_type(tp, key)` beside `_fixed_position`, `_namedtuple_index_spellings` is derived from the same range, and the table names one entry for the subject.
See [namedtuple-is-a-fixed-length-sequence.md](../../architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence).

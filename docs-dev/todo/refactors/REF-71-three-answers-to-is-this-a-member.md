---
filed: 2026-10-01
where:
  - src/confarg/_types.py::_union_tag_shadowed
  - src/confarg/_types.py::_struct_member_names
  - src/confarg/_parse_cli.py::_segment_names_real_field
  - src/confarg/_parse_cli.py::_member_names
  - src/confarg/_parse_cli.py::_advance_field_type
effort: M
risk: medium
impact: none
severity: trivial
---
# REF-71 — Four functions answer "does this segment name a member?", and they disagree at the edges

The walk's step, `_advance_field_type` (with `_walk_path` forking at unions), is what
decides whether a segment reaches a member. For a struct it asks `_types._struct_member_type`,
and so do the struct arms of `_segment_names_real_field` and `_union_tag_shadowed` (which closed
BUG-103's lag). What still restates the decision is the dispatch around that call:

- `_segment_names_real_field` counts the tag itself as a member (`seg == union_tag` → True),
  which mixes the casts/locals question with the membership one, and counts any key of a dict.
- `_union_tag_shadowed` has no namedtuple arm, so a custom tag spelled like a namedtuple field
  is not shadowed.
- REF-73 added a listing form for the env channel: `_parse_cli._member_names` (struct,
  namedtuple, union) over `_types._struct_member_names`. It has its own `_is_*` chain, asking
  namedtuple before struct where `_segment_names_real_field` asks struct before namedtuple, and
  its own subclass enumeration beside `_subclass_field_type`'s.

Under the current callers the gaps are latent *(inferred — no failing case observed)*. Fix
direction: one membership answer per node, `_member_names` dispatching on `_type_kind`, with
the predicates expressed through it (`seg in _member_names(pt)`, plus the dict and tag
short-circuits at the casts/locals callers that want them), and `_struct_member_names`
derived from `_struct_member_type`. Update the rows of the canonical table in
[invariants.md](../../architecture/invariants.md#delegate-to-the-canonical-function).

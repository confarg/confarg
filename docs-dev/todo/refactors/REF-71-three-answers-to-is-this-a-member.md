# REF-71 — Three functions answer "does this segment name a member?", and they disagree at the edges

**Where:** `src/confarg/_types.py` (`_union_tag_shadowed`) · `src/confarg/_parse_cli.py`
(`_segment_names_real_field`, `_advance_field_type`) · **Filed:** 2026-10-01
**Effort:** M · **Risk:** medium · **Impact:** none

The walk's step, `_advance_field_type` (with `_field_types` recursing into unions), is what
decides whether a segment reaches a member. Two predicates restate that decision instead of
asking it:

- `_union_tag_shadowed` describes itself as "the walk's member answer". BUG-103 was this copy
  lagging the walk: it had no subclass-only field arm.
- `_segment_names_real_field` counts the tag itself as a member (`seg == union_tag` → True),
  which mixes the casts/locals question with the membership one.

They still disagree on namedtuples (a custom tag spelled like a namedtuple field) and dicts
(any key is a member). Under the current callers the gaps are latent *(inferred — no failing
case observed)*. Fix direction: express both predicates through the walk's step, keeping the
tag-is-a-member short-circuit at the casts/locals callers that want it, and update the two
rows of the canonical table in
[invariants.md](../../architecture/invariants.md#delegate-to-the-canonical-function).

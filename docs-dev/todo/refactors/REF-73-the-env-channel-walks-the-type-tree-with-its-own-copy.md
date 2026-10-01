# REF-73 — The env channel walks the type tree with its own copy

**Where:** `src/confarg/_parse_env.py` (`_resolve_env_parts`, `_match_env_part`,
`_match_struct_part`, `_match_union_part`, `_match_namedtuple_part`, `_match_tuple_part`) ·
**Filed:** 2026-10-01
**Effort:** L · **Risk:** high · **Impact:** none

`_match_env_part` is a second type walk next to `_parse_cli._advance_field_type` /
`_resolve_field_type`. Its real job is case-insensitive matching plus two ambiguity errors.
Every rule the canonical walk gains has to be copied into it:

- BUG-101 copied the tag fallback;
- BUG-104 is the subclass-only field it lacks;
- BUG-108 is index spellings it accepts and the walk refuses;
- unions that disagree answer `None` here and `str` in the walk.

Another symptom, observed: `APP_PT__-1=5` on a namedtuple `pt` merges as `{'pt': {'-1': '5'}}`
(uncoerced, because the copy has no negative index and drops the type), while `--pt.-1 5` merges
`{'pt': {'-1': 5}}`.

Fix direction: reduce the env side to one step, mapping a segment to the exact spelling of the
member it names, then call the canonical walk. The case-insensitive part is then the only
env-specific rule. REF-43 kept this walk out of its own scope until there was a parity ruling;
the bugs above are that ruling, one case at a time. REF-47 (dispatch order) and REF-61 (index
guards) overlap and would close with it. See
[invariants.md#delegate-to-the-canonical-function](../../architecture/invariants.md#delegate-to-the-canonical-function).

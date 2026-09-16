# REF-23 — `_build_leaf_spec` repeats `group` / `group_description` on every FlagSpec

**Where:** `src/confarg/cli/_build.py` (`_build_leaf_spec`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** none

Seven `FlagSpec(...)` constructors in `_build_leaf_spec` (lines 117-207) each repeat
`group=group, group_description=group_description`. Build the common kwargs once (`common = dict(group=
group, group_description=group_description, help=help_text)`) and splat it, so each branch specifies
only what differs (`name`, `metavar`, `nargs`, `choices`). Removes ~14 repeated kwarg lines.

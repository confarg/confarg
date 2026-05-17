# REF-68 — the scalar root spec undoes the multi-token shape one attribute at a time

**Where:** `src/confarg/cli/_build.py` (`_scalar_root_spec`) · **Filed:** 2026-09-28
**Effort:** S · **Risk:** low · **Impact:** none

`_scalar_root_spec` builds the root flag through `_build_leaf_spec` and then clears, by hand, each
attribute the collection branch set: `nargs`, then `accumulates` (BUG-37), then `stands_bare`
(BUG-38). A `list[int]` root takes exactly one token
([03-cli-parsing.md#cli_prefix](../../architecture/03-cli-parsing.md#cli_prefix)), so every
attribute qualifying the multi-token shape has to be reset there — and the next one added to
`FlagSpec` will be forgotten, silently, because nothing ties the reset to the shape it undoes.

Three ways out, cheapest first: a `dataclasses.replace` with a single `_SINGLE_TOKEN` mapping of
the shape attributes; a `FlagSpec.as_single_token()` next to the attributes themselves, so the
model owns its own inverse; or not going through `_build_leaf_spec` at all, since the root flag
wants only the metavar the leaf branch computes. Prefer whichever keeps the reset beside the
attributes rather than beside the caller.

A test would help either way: `_scalar_root_spec(list[int])` should equal the spec for a
scalar root of the element type in every shape attribute, which is a property the current three
assignments assert by hand.

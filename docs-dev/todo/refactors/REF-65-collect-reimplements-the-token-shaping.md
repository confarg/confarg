# REF-65 — `cli/_collect.py` re-implements the token shaping `_parse_cli` now owns

**Where:** `src/confarg/cli/_collect.py` · **Filed:** 2026-09-28
**Effort:** S · **Risk:** medium · **Impact:** none

Shaping a multi-token flag's tokens into a value is now one pair of functions in the vanilla
parser, `_parse_cli._varlen_value` and `_union_seq_value`, both taking `(type, tokens)`, both
built on `_lone_json_array`. `_collect.py` answers the same question a second time in
`_coerce_leaf_value`, `_collect_union_seq_value` and `_json_array_override` — written to mirror
vanilla, and by hand, so the two have to keep agreeing forever. The mirror is sanctioned
([04-cli-adapters.md#byte-identical-merged-dicts](../../architecture/04-cli-adapters.md#byte-identical-merged-dicts))
but the signatures now line up exactly and `_collect.py` already imports from `_parse_cli`, so it
can delegate instead
([09-invariants.md#delegate-to-the-canonical-function](../../architecture/09-invariants.md#delegate-to-the-canonical-function)).

`_require_fixed_arity` joined them with BUG-58: it counts the token run vanilla counts one
`_require_value` at a time, so it is the fourth mirror and belongs in the same move.

The contract suite is what catches a drift today, which is why this is medium rather than low: a
mistake stays silent in the four adapters while vanilla stays right.

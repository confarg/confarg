# REF-43 — Four copies of the type-tree path walk in `_parse_cli.py`

**Where:** `src/confarg/_parse_cli.py` (`_resolve_field_type`, `_addresses_callable_key`,
`_is_collection_patch_path`, `_is_dict_at_path`) · **Filed:** 2026-09-24
**Effort:** M · **Risk:** high · **Impact:** none

Three of these are the same loop with a one-line question in the middle: `_resolve_type`, the
`union_tag` check, union recursion over `_union_args_no_none`, `_advance_field_type`, bail on
`None`. The `noqa` comment on `_is_collection_patch_path` already admits it is "mirroring
`_advance_field_type`". `_is_dict_at_path` is a fourth variant that re-runs `_resolve_field_type`
once per prefix, so it walks the type tree O(n²) times per token.

Fix direction: one `_walk_path(target, parts, union_tag)` generator carrying the union-recursion
contract, with each predicate reduced to five or eight lines over it.

Risk is **high** deliberately: three of these four are named canonical decision-makers in
[09-invariants.md#delegate-to-the-canonical-function](../../architecture/09-invariants.md#delegate-to-the-canonical-function)
— "does this segment name a real member?", "is this path a collection patch?", "does this token
address a callable key?" — and a mistake in the shared walk is silent in every channel and every
front-end at once. Closing this means extending the cross-channel contract suite.

Related, same family, and best done in the same pass: `_parse_env._accepts_json_for` re-derives
`_accepts_object_value` and `_types._is_seq_variant` instead of calling them, which is how
[BUG-39](../bugs/BUG-39-plain-class-whole-value-cli-only.md) came about.

The walk in `_parse_env._match_env_part` is **not** in scope. Env adds case-insensitive matching
and two ambiguity errors, and its struct branch lacks the `_subclass_field_type` fallback the CLI
has, so unifying the two would change behavior silently. Only the tuple, list and dict arms are
safe there; the rest needs a parity ruling first.

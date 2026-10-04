# REF-43 — Four copies of the type-tree path walk in `_parse_cli.py`

**Where:** `src/confarg/_parse_cli.py` (`_field_types`, `_addresses_callable_key`,
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
[invariants.md#delegate-to-the-canonical-function](../../architecture/invariants.md#delegate-to-the-canonical-function)
— "does this segment name a real member?", "is this path a collection patch?", "does this token
address a callable key?" — and a mistake in the shared walk is silent in every channel and every
front-end at once. Closing this means extending the cross-channel contract suite.

The same family, one member already closed: `_parse_env._accepts_json_for` used to re-derive
`_accepts_object_value` and `_types._is_seq_variant` instead of calling them, which is how BUG-39
came about; closing that bug reduced it to the two calls. Nothing is left of it to fold into this
pass — it is here as the precedent for what the walk should end up looking like.

The env channel has no walk of its own left to fold in: since REF-73 it spells each segment
case-insensitively and asks `_field_types` (which branches reach the prefix) and
`_resolve_field_type` (its fold) for the rest, so it inherits whatever this pass does to the
walk. `_field_types` already returns the per-branch answer a `_walk_path` generator would yield
at the end of the path.

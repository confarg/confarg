# REF-33 — `_build_leaf_spec` carries a dead `tuple[X, ...]` fallback branch

**Where:** `src/confarg/cli/_build.py` (`_build_leaf_spec`) · **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

The `else` arm after `_tuple_types(core) is not None` (the `tuple[X, ...]`
variable-length fallback, marked `# pragma: no cover`) is unreachable.
`_is_varlen_collection(core)` is tested first and returns `True` for
`tuple[X, ...]` (see `_types._is_varlen_collection`), so a variable-length
tuple never reaches the `_is_tuple` branch; a fixed-length tuple always has
`_tuple_types` non-None. The code already says so in its comment. Delete the
`else` arm (and drop the `if tt is not None` guard, returning directly);
nothing changes. Link:
[04-cli-adapters.md#whole-value-flags](../../architecture/04-cli-adapters.md#whole-value-flags).

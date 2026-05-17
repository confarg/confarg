# FEAT-4 — An explicit ordered patch-op stream

**Effort:** M *(design pass; implementation not sized)* · **Risk:** high · **Impact:** none

Vanilla and the adapters agree on collection patches because the adapters re-run the vanilla
parse loop in `patch_only` mode. An ordered stream of patch operations, produced once and
consumed by both, would make that parity structural instead of behavioral.
See [04-cli-adapters.md#collection-patch-parity](../../architecture/04-cli-adapters.md#collection-patch-parity).

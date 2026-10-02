# FEAT-4 — An explicit ordered patch-op stream

**Effort:** M *(design pass; implementation not sized)* · **Risk:** high · **Impact:** none

Vanilla and the adapters agree on collection patches because the adapters re-run the vanilla
parse loop in `patch_only` mode. An ordered stream of patch operations, produced once and
consumed by both, would make that parity structural instead of behavioral.
See [04-cli-adapters.md#collection-patch-parity](../../architecture/04-cli-adapters.md#collection-patch-parity).

[FEAT-23](FEAT-23-post-resolve-transform-layer.md) introduces an op record of its own for declared
transforms. Whether one stream can serve both — user-facing transforms and vanilla/adapter collection
patches — is worth deciding once that engine exists, and not before: the two answer different
questions today, and asserting they are the same is what this ticket has to establish rather than
assume.

# FEAT-4 — An explicit ordered patch-op stream

**Effort:** M *(design pass; implementation not sized)* · **Risk:** high · **Impact:** none

Vanilla and the adapters agree on collection patches structurally since REF-72: the adapters'
CLI channel is the vanilla parse loop itself, so parity no longer motivates an explicit stream.
What is left is whether patch operations should be an ordered stream of records, produced once
and consumed by `build()`, rather than ops encoded into the merged dict's shape.
See [cli-adapters/collection-patch-parity.md#collection-patch-parity](../../architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity).

[FEAT-23](FEAT-23-post-resolve-transform-layer.md) introduces an op record of its own for declared
transforms. Whether one stream can serve both — user-facing transforms and vanilla/adapter collection
patches — is worth deciding once that engine exists, and not before: the two answer different
questions today, and asserting they are the same is what this ticket has to establish rather than
assume.

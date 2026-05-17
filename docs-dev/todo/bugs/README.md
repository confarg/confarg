# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from
the documented intent. One ticket per file; see [../README.md](../README.md) for the format,
including the [reproduction](../README.md#reproduction) every entry here carries.

Cross-channel parity is mandatory
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)),
so a parity entry here is a violation nobody has approved, not a design choice.

<!-- tickets:start -->

| Ticket | Effort | Risk | Impact |
|---|---|---|---|
| [BUG-3 — A root-level JSON cast is refused in the environment](BUG-3-root-json-cast-refused-in-env.md) | M | high | behavior |
| [BUG-4 — Stealing order does not match the documented rule](BUG-4-stealing-order-mismatch.md) | M | high | config |
| [BUG-7 — Typer integration is claimed, never tested, and currently broken](BUG-7-typer-claimed-untested-broken.md) | L | medium | behavior |
| [BUG-15 — `dump()` drops a leaf a union variant will steal back](BUG-15-dump-drops-stolen-leaf.md) | L | medium | config |
| [BUG-24 — A delete flag drops the callable shorthand it refines in the adapters](BUG-24-delete-flag-drops-callable-shorthand.md) | M | high | behavior |
| [BUG-26 — Architecture notes link closed tickets to a board that cannot hold them](BUG-26-architecture-links-closed-tickets.md) | S | low | none |
| [BUG-27 — A value starting with `--` is refused by the vanilla parser](BUG-27-dash-prefixed-value-rejected.md) | M | high | config |
| [BUG-28 — A callable's sibling kwarg the signature does not name is vanilla-only](BUG-28-callable-sibling-kwarg-unregistered.md) | S | medium | config |

<!-- tickets:end -->

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
| [BUG-7 — Typer integration is claimed, never tested, and currently broken](BUG-7-typer-claimed-untested-broken.md) | L | medium | behavior |
| [BUG-26 — Architecture notes link closed tickets to a board that cannot hold them](BUG-26-architecture-links-closed-tickets.md) | S | low | none |
| [BUG-27 — A value starting with `--` is refused by the vanilla parser](BUG-27-dash-prefixed-value-rejected.md) | M | high | config |
| [BUG-28 — A callable's sibling kwarg the signature does not name is vanilla-only](BUG-28-callable-sibling-kwarg-unregistered.md) | S | medium | config |
| [BUG-29 — A bind subkey's delete flag is registered as if it took a value](BUG-29-bind-subkey-delete-registered-with-a-value.md) | S | medium | config |
| [BUG-30 — The argv opener scan reads a struct field named `fn` as a callable opener](BUG-30-opener-scan-ignores-the-field-type.md) | M | medium | config |
| [BUG-31 — `dump()` crashes on a union with a subscripted or `Literal` variant](BUG-31-dump-crashes-on-generic-union-variant.md) | M | medium | behavior |

<!-- tickets:end -->

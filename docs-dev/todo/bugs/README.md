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
| [BUG-34 — YAML root config file with a non-dict top-level value silently loads empty](BUG-34-yaml-non-dict-root-silent-empty.md) | S | medium | behavior |

<!-- tickets:end -->

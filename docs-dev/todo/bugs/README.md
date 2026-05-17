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
| [BUG-35 — A mixed append (`--f+ v` and a bare `--f+`) is rejected by three front-ends](BUG-35-mixed-append-spelling-rejected-by-three-front-ends.md) | M | low | behavior |
| [BUG-36 — `index.py` rewrites a board table without the ticket it just failed to parse](BUG-36-index-drops-the-row-of-a-ticket-it-cannot-parse.md) | S | low | none |
| [BUG-37 — A repeated varlen flag accumulates in three front-ends and last-wins in two](BUG-37-repeated-varlen-flag-accumulates-in-three-front-ends.md) | M | medium | behavior |
| [BUG-38 — A bare `--<list>` clears the list everywhere except click and typer](BUG-38-bare-varlen-flag-rejected-by-the-clicklike-front-ends.md) | S | low | behavior |

<!-- tickets:end -->

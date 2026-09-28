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
| [BUG-36 — `index.py` rewrites a board table without the ticket it just failed to parse](BUG-36-index-drops-the-row-of-a-ticket-it-cannot-parse.md) | S | low | none |
| [BUG-37 — A repeated varlen flag accumulates in three front-ends and last-wins in two](BUG-37-repeated-varlen-flag-accumulates-in-three-front-ends.md) | M | medium | behavior |
| [BUG-38 — A bare `--<list>` clears the list everywhere except click and typer](BUG-38-bare-varlen-flag-rejected-by-the-clicklike-front-ends.md) | S | low | behavior |
| [BUG-39 — A plain class takes a whole `{…}` value from env and files, but not from the CLI](BUG-39-plain-class-whole-value-cli-only.md) | S | high | config |
| [BUG-40 — `_StrToken` leaks into user-facing error messages](BUG-40-strtoken-leaks-into-error-messages.md) | S | low | behavior |
| [BUG-41 — A class nested inside a class does not round-trip its union tag](BUG-41-nested-class-tag-dumps-name-not-qualname.md) | S | medium | config |
| [BUG-43 — A fixed-arity tuple flag under-fills instead of reporting a missing value](BUG-43-fixed-tuple-flag-skips-the-missing-value-check.md) | S | medium | behavior |
| [BUG-44 — `_dataclass_subclasses` returns a diamond subclass twice, and is not BFS](BUG-44-dataclass-subclasses-duplicates-and-is-not-bfs.md) | S | medium | behavior |
| [BUG-45 — An unimportable class tag silently vanishes from the adapters' merged dict](BUG-45-inheritance-tag-dropped-on-unimportable-class.md) | S | medium | behavior |
| [BUG-46 — The `90_integration` code blocks document an API that does not exist](BUG-46-old-help-blocks-document-a-removed-api.md) | S | low | none |
| [BUG-47 — The CSV section of `11_include` is cut off mid-sentence](BUG-47-include-readme-truncates-the-csv-header-section.md) | S | low | none |
| [BUG-48 — `12_collections` cites "Tutorial XX" instead of a real tutorial](BUG-48-collections-readme-defers-to-tutorial-xx.md) | S | low | none |
| [BUG-49 — A `Dev Notes:` citation points at `#the-triad`, a heading renamed to `## The quartet`](BUG-49-stale-the-triad-citation.md) | S | low | none |
| [BUG-50 — A `--config.<subpath>` naming no field mounts silently, and dict fields get no flag](BUG-50-config-subpath-is-never-checked-against-the-target.md) | M | medium | behavior |
| [BUG-51 — A bare `--config.<subpath>+` is an error in vanilla and a no-op in two front-ends](BUG-51-bare-config-append-accepted-by-two-front-ends.md) | S | low | behavior |

<!-- tickets:end -->

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
| [BUG-45 — An unimportable class tag silently vanishes from the adapters' merged dict](BUG-45-inheritance-tag-dropped-on-unimportable-class.md) | S | medium | behavior |
| [BUG-46 — The `90_integration` code blocks document an API that does not exist](BUG-46-old-help-blocks-document-a-removed-api.md) | S | low | none |
| [BUG-47 — The CSV section of `11_include` is cut off mid-sentence](BUG-47-include-readme-truncates-the-csv-header-section.md) | S | low | none |
| [BUG-48 — `12_collections` cites "Tutorial XX" instead of a real tutorial](BUG-48-collections-readme-defers-to-tutorial-xx.md) | S | low | none |
| [BUG-50 — A `--config.<subpath>` naming no field mounts silently, and dict fields get no flag](BUG-50-config-subpath-is-never-checked-against-the-target.md) | M | medium | behavior |
| [BUG-53 — a whole-field delete wins over a later flag in the adapters, not in vanilla](BUG-53-whole-field-delete-beats-a-later-flag-in-the-adapters.md) | M | medium | config |
| [BUG-54 — A plain collection flag does not discard the patch ops before it in the adapters](BUG-54-plain-occurrence-does-not-discard-earlier-patch-ops-in-the-adapters.md) | M | medium | config |
| [BUG-56 — The flat spelling of the tagged-leaf hatch reaches no adapter](BUG-56-flat-tagged-leaf-flags-unregistered-by-the-adapters.md) | M | medium | behavior |
| [BUG-61 — A bare optional fixed-arity flag clears in the adapters and raises in vanilla](BUG-61-optional-fixed-arity-bare-flag-clears-in-the-adapters.md) | M | medium | behavior |
| [BUG-62 — Cyclopts accumulates a repeated fixed-arity flag instead of letting the last one win](BUG-62-cyclopts-accumulates-a-repeated-fixed-arity-flag.md) | M | medium | behavior |
| [BUG-63 — A bare `--config` before `--help` shows help on argparse and errors on the other four](BUG-63-bare-config-before-help-shows-help-on-argparse.md) | S | medium | behavior |
| [BUG-65 — An index sub-flag is renamed and dropped in the adapters](BUG-65-namedtuple-index-sub-flag-renamed-and-dropped-in-the-adapters.md) | S | medium | behavior |
| [BUG-67 — A plain fixed tuple's index patch lands as the applied value in the adapters, as a list-op dict in vanilla](BUG-67-plain-tuple-index-patch-applied-instead-of-recorded-in-the-adapters.md) | M | medium | behavior |
| [BUG-68 — A sub-flag more than one level below a namedtuple field is accepted only by vanilla](BUG-68-deep-sub-flags-below-a-namedtuple-reach-no-adapter.md) | M | medium | behavior |

<!-- tickets:end -->

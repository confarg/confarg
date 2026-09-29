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
| [BUG-44 — `_dataclass_subclasses` returns a diamond subclass twice, and is not BFS](BUG-44-dataclass-subclasses-duplicates-and-is-not-bfs.md) | S | medium | behavior |
| [BUG-45 — An unimportable class tag silently vanishes from the adapters' merged dict](BUG-45-inheritance-tag-dropped-on-unimportable-class.md) | S | medium | behavior |
| [BUG-46 — The `90_integration` code blocks document an API that does not exist](BUG-46-old-help-blocks-document-a-removed-api.md) | S | low | none |
| [BUG-47 — The CSV section of `11_include` is cut off mid-sentence](BUG-47-include-readme-truncates-the-csv-header-section.md) | S | low | none |
| [BUG-48 — `12_collections` cites "Tutorial XX" instead of a real tutorial](BUG-48-collections-readme-defers-to-tutorial-xx.md) | S | low | none |
| [BUG-49 — A `Dev Notes:` citation points at `#the-triad`, a heading renamed to `## The quartet`](BUG-49-stale-the-triad-citation.md) | S | low | none |
| [BUG-50 — A `--config.<subpath>` naming no field mounts silently, and dict fields get no flag](BUG-50-config-subpath-is-never-checked-against-the-target.md) | M | medium | behavior |
| [BUG-51 — A bare `--config.<subpath>+` is an error in vanilla and a no-op in two front-ends](BUG-51-bare-config-append-accepted-by-two-front-ends.md) | S | low | behavior |
| [BUG-52 — `tests/examples/_registry.py` imports a harness that is not in the tree](BUG-52-examples-registry-imports-a-missing-harness.md) | S | low | none |
| [BUG-53 — a whole-field delete wins over a later flag in the adapters, not in vanilla](BUG-53-whole-field-delete-beats-a-later-flag-in-the-adapters.md) | M | medium | config |
| [BUG-54 — A plain collection flag does not discard the patch ops before it in the adapters](BUG-54-plain-occurrence-does-not-discard-earlier-patch-ops-in-the-adapters.md) | M | medium | config |
| [BUG-55 — Two ticket reproductions run as tests and fail on every full suite](BUG-55-two-ticket-reproductions-run-as-tests-and-fail.md) | S | low | none |
| [BUG-56 — The flat spelling of the tagged-leaf hatch reaches no adapter](BUG-56-flat-tagged-leaf-flags-unregistered-by-the-adapters.md) | M | medium | behavior |
| [BUG-58 — The argparse and cyclopts adapters still under-fill a fixed-arity flag](BUG-58-adapters-underfill-a-fixed-arity-flag.md) | M | medium | behavior |
| [BUG-59 — A fixed-arity flag's elements are not eagerly coerced in any adapter](BUG-59-fixed-arity-elements-not-eagerly-coerced-in-the-adapters.md) | S | medium | behavior |

<!-- tickets:end -->

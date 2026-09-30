# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from
the documented intent. One ticket per file; see [../README.md](../README.md) for the format,
including the [reproduction](../README.md#reproduction) every entry here carries.

Cross-channel parity is mandatory
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)),
so a parity entry here is a violation nobody has approved, not a design choice.

<!-- tickets:start -->

| Ticket | Effort | Risk | Impact |
|---|---|---|---|
| [BUG-46 — The `90_integration` code blocks document an API that does not exist](BUG-46-old-help-blocks-document-a-removed-api.md) | S | low | none |
| [BUG-47 — The CSV section of `11_include` is cut off mid-sentence](BUG-47-include-readme-truncates-the-csv-header-section.md) | S | low | none |
| [BUG-48 — `12_collections` cites "Tutorial XX" instead of a real tutorial](BUG-48-collections-readme-defers-to-tutorial-xx.md) | S | low | none |
| [BUG-61 — A bare optional fixed-arity flag clears in the adapters and raises in vanilla](BUG-61-optional-fixed-arity-bare-flag-clears-in-the-adapters.md) | M | medium | behavior |
| [BUG-63 — A bare `--config` before `--help` shows help on argparse and errors on the other four](BUG-63-bare-config-before-help-shows-help-on-argparse.md) | S | medium | behavior |
| [BUG-65 — An index sub-flag is renamed and dropped in the adapters](BUG-65-namedtuple-index-sub-flag-renamed-and-dropped-in-the-adapters.md) | S | medium | behavior |
| [BUG-67 — A plain fixed tuple's index patch lands as the applied value in the adapters, as a list-op dict in vanilla](BUG-67-plain-tuple-index-patch-applied-instead-of-recorded-in-the-adapters.md) | M | medium | behavior |
| [BUG-68 — A sub-flag more than one level below a namedtuple field is accepted only by vanilla](BUG-68-deep-sub-flags-below-a-namedtuple-reach-no-adapter.md) | M | medium | behavior |
| [BUG-69 — With a class tag present, the adapters drop the other variants' flags](BUG-69-tag-present-drops-other-variants-flags.md) | M | medium | behavior |
| [BUG-70 — A union-of-structs field is a mount point with no `--config.<field>` entry](BUG-70-union-of-structs-mount-point-has-no-help-entry.md) | S | low | behavior |
| [BUG-71 — The flat tagged-leaf hatch on a scalar root reaches no adapter](BUG-71-flat-tagged-leaf-hatch-unreachable-on-a-scalar-root.md) | S | medium | behavior |
| [BUG-72 — Scalar force-cast flags on non-union fields reach no adapter](BUG-72-scalar-force-cast-flags-unregistered-on-plain-fields.md) | S | medium | behavior |
| [BUG-74 — Cyclopts asserts on a bare fixed-arity occurrence beside a valued one](BUG-74-cyclopts-asserts-on-a-bare-fixed-arity-occurrence-beside-a-valued-one.md) | S | low | behavior |
| [BUG-75 — Argparse alone refuses the tokens that complete a `=`-spelled fixed-arity run](BUG-75-argparse-alone-refuses-the-tokens-completing-an-equals-spelled-fixed-arity-run.md) | S | medium | behavior |
| [BUG-77 — An index delete below a whole-field delete crashes the patch scan](BUG-77-an-index-delete-below-a-whole-field-delete-crashes-the-patch-scan.md) | S | high | behavior |
| [BUG-78 — Cyclopts refuses a delete flag spelled twice](BUG-78-cyclopts-refuses-a-delete-flag-spelled-twice.md) | S | low | behavior |

<!-- tickets:end -->

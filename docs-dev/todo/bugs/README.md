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
| [BUG-63 — A bare `--config` before `--help` shows help on argparse and errors on the other four](BUG-63-bare-config-before-help-shows-help-on-argparse.md) | S | medium | behavior |
| [BUG-75 — Argparse alone refuses the tokens that complete a `=`-spelled fixed-arity run](BUG-75-argparse-alone-refuses-the-tokens-completing-an-equals-spelled-fixed-arity-run.md) | S | medium | behavior |
| [BUG-77 — An index delete below a whole-field delete crashes the patch scan](BUG-77-an-index-delete-below-a-whole-field-delete-crashes-the-patch-scan.md) | S | high | behavior |
| [BUG-78 — Cyclopts refuses a delete flag spelled twice](BUG-78-cyclopts-refuses-a-delete-flag-spelled-twice.md) | S | low | behavior |
| [BUG-85 — A struct field's bare flag typed after its sub-flag loses to the sub-flag on the adapters](BUG-85-bare-flag-typed-after-its-subflag-loses-on-the-adapters.md) | M | medium | behavior |
| [BUG-86 — A subclass's override of a base-declared field is coerced by the last subclass walk](BUG-86-a-subclass-override-of-a-base-field-is-coerced-by-the-last-walk.md) | M | medium | behavior |
| [BUG-87 — The adapters' merged dict orders keys by the walk, not by argv, so a dump differs byte for byte](BUG-87-merged-dict-key-order-follows-the-walk-not-argv.md) | M | medium | behavior |
| [BUG-88 — A mount point below a direct root field has no `--config.<path>` entry](BUG-88-a-mount-point-below-a-direct-root-field-has-no-config-entry.md) | L | medium | behavior |
| [BUG-89 — `test_str_round_trip` draws dashed values the space form refuses by design](BUG-89-test-str-round-trip-draws-dashed-values-the-space-form-refuses.md) | S | low | none |
| [BUG-90 — The env channel drops a root-level CLASS variable on a struct-walked root](BUG-90-env-channel-drops-a-root-level-class-variable.md) | S | medium | behavior |
| [BUG-91 — Vanilla silently drops the bare prefix flag's value on a struct-like root](BUG-91-vanilla-drops-the-bare-prefix-flag-value-on-a-struct-root.md) | S | medium | behavior |
| [BUG-92 — The adapters reject a root tag on a subclass-less struct root that vanilla accepts](BUG-92-adapters-reject-a-root-tag-on-a-subclass-less-struct-root.md) | S | medium | behavior |
| [BUG-93 — Scalar cast flags stay refused on struct, collection and registered-leaf fields](BUG-93-scalar-cast-flags-stay-refused-on-struct-collection-and-leaf-fields.md) | M | medium | behavior |
| [BUG-94 — Multi-variant unions refuse the scalar casts beyond the union's own scalars](BUG-94-multi-variant-unions-refuse-casts-beyond-their-own-scalars.md) | S | medium | behavior |
| [BUG-95 — A union's cast flag beats its plain flag whatever order they were typed in](BUG-95-a-union-cast-flag-beats-its-plain-flag-whatever-the-argv-order.md) | S | medium | behavior |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | M | low | behavior |
| [BUG-97 — A namedtuple's -0 and +0 index spellings diverge across the front-ends](BUG-97-a-namedtuples-minus-zero-and-plus-zero-index-spellings-diverge.md) | S | low | behavior |

<!-- tickets:end -->

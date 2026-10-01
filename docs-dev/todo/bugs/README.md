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
| [BUG-86 — A subclass's override of a base-declared field is coerced by the last subclass walk](BUG-86-a-subclass-override-of-a-base-field-is-coerced-by-the-last-walk.md) | M | medium | behavior |
| [BUG-87 — The adapters' merged dict orders keys by the walk, not by argv, so a dump differs byte for byte](BUG-87-merged-dict-key-order-follows-the-walk-not-argv.md) | M | medium | behavior |
| [BUG-88 — A mount point below a direct root field has no `--config.<path>` entry](BUG-88-a-mount-point-below-a-direct-root-field-has-no-config-entry.md) | L | medium | behavior |
| [BUG-93 — Scalar cast flags stay refused on struct, collection and registered-leaf fields](BUG-93-scalar-cast-flags-stay-refused-on-struct-collection-and-leaf-fields.md) | M | medium | behavior |
| [BUG-94 — Multi-variant unions refuse the scalar casts beyond the union's own scalars](BUG-94-multi-variant-unions-refuse-casts-beyond-their-own-scalars.md) | S | medium | behavior |
| [BUG-95 — A union's cast flag beats its plain flag whatever the argv order](BUG-95-a-union-cast-flag-beats-its-plain-flag-whatever-the-argv-order.md) | S | medium | behavior |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | M | low | behavior |
| [BUG-98 — A dict-key delete with no base dict errors on the leaked `_DeleteSentinel`](BUG-98-a-dict-key-delete-with-no-base-dict-leaks-the-delete-sentinel.md) | S | low | behavior |
| [BUG-104 — The env walk cannot see a subclass-only field, so the tag wins a case-differing spelling](BUG-104-the-env-walk-cannot-see-a-subclass-only-field-so-the-tag-wins-a-case-differing-spelling.md) | S | medium | config |
| [BUG-105 — The anchor sweep cannot see citations under `tests/`, nor short-form spellings](BUG-105-the-anchor-sweep-cannot-see-citations-under-tests-or-short-form-spellings.md) | S | medium | none |
| [BUG-107 — A real field named like the tag, nested inside a union variant, is stripped by the type check](BUG-107-a-nested-real-field-named-like-the-tag-is-stripped-by-the-union-type-check.md) | S | medium | behavior |
| [BUG-108 — A plain fixed tuple accepts the index spellings a namedtuple refuses](BUG-108-a-plain-fixed-tuple-accepts-the-index-spellings-a-namedtuple-refuses.md) | S | medium | behavior |
| [BUG-109 — A namedtuple index patch ignores the field's default, where a tuple patch keeps it](BUG-109-a-namedtuple-index-patch-ignores-the-fields-default.md) | S | medium | behavior |
| [BUG-110 — The walk accepts a path that continues past the union tag](BUG-110-the-walk-accepts-a-path-that-continues-past-the-tag.md) | S | medium | behavior |
| [BUG-111 — A bare flag between its sub-flags keeps the sub-flags before it on the adapters](BUG-111-a-bare-flag-between-its-sub-flags-keeps-the-sub-flags-before-it-on-the-adapters.md) | L | medium | behavior |
| [BUG-112 — A namedtuple's non-struct field takes scalar flags on the adapters](BUG-112-a-namedtuples-non-struct-field-takes-scalar-flags-on-the-adapters.md) | M | medium | behavior |
| [BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters](BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md) | M | medium | behavior |
| [BUG-114 — Cyclopts cannot register subclasses that share a struct field name](BUG-114-cyclopts-cannot-register-subclasses-that-share-a-struct-field-name.md) | S | medium | behavior |
| [BUG-115 — Every prefixed environment variable overwrites a scalar root](BUG-115-every-prefixed-env-var-overwrites-a-scalar-root.md) | S | low | behavior |
| [BUG-116 — An env whole-field delete beside a sub-path variable depends on the mapping's order](BUG-116-an-env-whole-field-delete-beside-a-sub-path-var-depends-on-mapping-order.md) | S | low | behavior |

<!-- tickets:end -->

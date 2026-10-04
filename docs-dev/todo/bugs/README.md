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
| [BUG-88 — A mount point below a direct root field has no `--config.<path>` entry](BUG-88-a-mount-point-below-a-direct-root-field-has-no-config-entry.md) | L | medium | behavior |
| [BUG-93 — Scalar cast flags stay refused on struct, collection and registered-leaf fields](BUG-93-scalar-cast-flags-stay-refused-on-struct-collection-and-leaf-fields.md) | S | medium | behavior |
| [BUG-94 — Multi-variant unions refuse the scalar casts beyond the union's own scalars](BUG-94-multi-variant-unions-refuse-casts-beyond-their-own-scalars.md) | S | medium | behavior |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | M | low | behavior |
| [BUG-98 — A dict-key delete with no base dict errors on the leaked `_DeleteSentinel`](BUG-98-a-dict-key-delete-with-no-base-dict-leaks-the-delete-sentinel.md) | S | low | behavior |
| [BUG-105 — The anchor sweep cannot see citations under `tests/`, nor short-form spellings](BUG-105-the-anchor-sweep-cannot-see-citations-under-tests-or-short-form-spellings.md) | S | medium | none |
| [BUG-107 — A real field named like the tag, nested inside a union variant, is stripped by the type check](BUG-107-a-nested-real-field-named-like-the-tag-is-stripped-by-the-union-type-check.md) | S | medium | behavior |
| [BUG-108 — A plain fixed tuple accepts the index spellings a namedtuple refuses](BUG-108-a-plain-fixed-tuple-accepts-the-index-spellings-a-namedtuple-refuses.md) | S | medium | behavior |
| [BUG-109 — A namedtuple index patch ignores the field's default, where a tuple patch keeps it](BUG-109-a-namedtuple-index-patch-ignores-the-fields-default.md) | S | medium | behavior |
| [BUG-110 — The walk accepts a path that continues past the union tag](BUG-110-the-walk-accepts-a-path-that-continues-past-the-tag.md) | S | medium | behavior |
| [BUG-112 — A namedtuple's non-struct field takes scalar flags on the adapters](BUG-112-a-namedtuples-non-struct-field-takes-scalar-flags-on-the-adapters.md) | M | medium | behavior |
| [BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters](BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md) | M | medium | behavior |
| [BUG-114 — Cyclopts cannot register subclasses that share a struct field name](BUG-114-cyclopts-cannot-register-subclasses-that-share-a-struct-field-name.md) | S | medium | behavior |
| [BUG-115 — Every prefixed environment variable overwrites a scalar root](BUG-115-every-prefixed-env-var-overwrites-a-scalar-root.md) | S | low | behavior |
| [BUG-116 — An env whole-field delete beside a sub-path variable depends on the mapping's order](BUG-116-an-env-whole-field-delete-beside-a-sub-path-var-depends-on-mapping-order.md) | S | low | behavior |
| [BUG-117 — A union with an `Any` variant refuses to load and crashes `dump()`](BUG-117-a-union-with-an-any-variant-refuses-to-load-and-crashes-dump.md) | M | high | behavior |
| [BUG-118 — `merge()`'s loading order names the env config pointer without its prefix](BUG-118-merge-docstring-names-the-env-config-pointer-without-its-prefix.md) | S | low | behavior |
| [BUG-119 — `_defaults.py` says four front-ends must agree; there are five](BUG-119-defaults-module-counts-four-front-ends.md) | S | low | none |
| [BUG-131 — A key named like an anchor stand-in is read as the anchor](BUG-131-a-key-named-like-an-anchor-stand-in-is-read-as-the-anchor.md) | M | high | behavior |
| [BUG-132 — A name Python normalizes reads another key](BUG-132-a-name-python-normalizes-reads-another-key.md) | M | high | config |
| [BUG-133 — An expression's list index accepts any spelling `int()` does](BUG-133-an-expression-list-index-accepts-any-int-spelling.md) | S | high | config |
| [BUG-134 — A miss off a value no path names is a bare repr](BUG-134-a-miss-off-a-value-no-path-names-is-a-bare-repr.md) | S | high | behavior |
| [BUG-135 — An operator or a call that fails names no expression](BUG-135-an-operator-or-call-error-names-no-expression.md) | S | high | behavior |
| [BUG-136 — The uncalled-method hint spells an anchored path as an absolute one](BUG-136-an-uncalled-method-hint-spells-an-anchored-path-absolute.md) | S | high | behavior |
| [BUG-137 — A too deeply nested expression escapes as a raw parser error](BUG-137-a-too-deeply-nested-expression-escapes-as-a-raw-parser-error.md) | S | high | behavior |

<!-- tickets:end -->

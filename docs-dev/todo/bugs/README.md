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
| [BUG-140 — The `from_namespace` / `from_context` docstrings still read the CLI channel out of the parse result](BUG-140-adapter-docstrings-read-the-cli-channel-out-of-the-parse-result.md) | S | low | behavior |
| [BUG-142 — A namedtuple built from a dict accepts index keys the CLI refuses](BUG-142-a-namedtuple-built-from-a-dict-accepts-index-keys-the-cli-refuses.md) | S | medium | config |
| [BUG-144 — The refusal of a method on a non-string reads "a int"](BUG-144-a-method-on-a-non-string-reads-a-int.md) | S | low | behavior |
| [BUG-145 — An expression that parses but nests past the recursion limit crashes the walkers](BUG-145-an-expression-that-parses-but-nests-past-the-recursion-limit-crashes-the-walkers.md) | M | high | behavior |
| [BUG-146 — A power or a repeated string has no size bound](BUG-146-a-power-or-a-repeated-string-has-no-size-bound.md) | L | high | config |
| [BUG-149 — The testing protocol routes example tests to a folder that does not exist](BUG-149-the-testing-protocol-routes-example-tests-to-a-folder-that-does-not-exist.md) | S | low | none |
| [BUG-150 — The protocols count four front-ends and leave typer out](BUG-150-the-protocols-count-four-front-ends-and-leave-typer-out.md) | S | low | none |
| [BUG-151 — The namedtuple decision names the bugs board by its old file](BUG-151-the-namedtuple-decision-names-the-bugs-board-by-its-old-file.md) | S | low | none |
| [BUG-152 — A positional-only `__init__` parameter fails `build()` with a raw `TypeError`](BUG-152-a-positional-only-init-parameter-fails-build-with-a-raw-typeerror.md) | S | high | behavior |
| [BUG-153 — A class without its own `__init__` is a struct with `args` and `kwargs` fields](BUG-153-a-class-without-its-own-init-is-a-struct-with-args-and-kwargs-fields.md) | S | high | config |
| [BUG-154 — An integer in a file is refused for a `float` field](BUG-154-an-integer-in-a-file-is-refused-for-a-float-field.md) | S | high | behavior |
| [BUG-155 — A `call:` spec naming a class passes its kwargs uncoerced](BUG-155-a-call-spec-naming-a-class-passes-its-kwargs-uncoerced.md) | S | high | behavior |
| [BUG-156 — A positional-only parameter in a callable spec is passed by keyword](BUG-156-a-positional-only-parameter-in-a-callable-spec-is-passed-by-keyword.md) | S | high | behavior |
| [BUG-171 — A short token run on a fixed-arity flag gets a one-value usage line](BUG-171-a-short-fixed-arity-run-gets-a-one-value-usage.md) | S | medium | behavior |
| [BUG-172 — An element flag below a collection root is silently dropped](BUG-172-an-element-flag-below-a-collection-root-is-silently-dropped.md) | L | medium | config |
| [BUG-173 — cyclopts crashes on a dict-key flag whose key is no identifier](BUG-173-cyclopts-crashes-on-a-dict-key-flag-that-is-no-identifier.md) | S | medium | behavior |
| [BUG-174 — An index delete on a dict writes the list-delete key into the dict](BUG-174-an-index-delete-on-a-dict-writes-the-list-delete-key.md) | S | medium | behavior |
| [BUG-175 — A file's list-delete key holding no index list escapes as a raw TypeError](BUG-175-a-files-list-delete-key-holding-no-index-list-escapes-as-a-typeerror.md) | S | low | none |

<!-- tickets:end -->

# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from
the documented intent. One ticket per file; see [../README.md](../README.md) for the format,
including the [reproduction](../README.md#reproduction) every entry here carries.

Cross-channel parity is mandatory
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)),
so a parity entry here is a violation nobody has approved, not a design choice.

<!-- tickets:start -->

| Ticket | Severity | Blocked by | Effort | Risk | Impact | Introduced by |
|---|---|---|---|---|---|---|
| [BUG-155 — A `call:` spec naming a class passes its kwargs uncoerced](BUG-155-a-call-spec-naming-a-class-passes-its-kwargs-uncoerced.md) | critical |  | S | high | behavior | PR-5 |
| [BUG-182 — An env delete naming no member is dropped without a warning](BUG-182-an-env-delete-naming-no-member-is-dropped-without-a-warning.md) | critical |  | S | low | behavior | PR-5 |
| [BUG-185 — A dict key `*` from a higher layer wipes the dict's other keys](BUG-185-a-dict-key-star-from-a-higher-layer-wipes-the-dicts-other-keys.md) | critical |  | S | high | behavior | BUG-160 |
| [BUG-186 — A root `json` cast swallows a field delete meant for the layers below](BUG-186-a-root-json-cast-swallows-a-field-delete-meant-for-the-layers-below.md) | critical |  | S | high | behavior | PR-87, BUG-3 |
| [BUG-179 — An element flag on a scalar swallows a stray token on argparse and cyclopts](BUG-179-an-element-flag-on-a-scalar-swallows-a-stray-token-on-argparse-and-cyclopts.md) | critical |  | M | medium | config | PR-72 |
| [BUG-146 — A power or a repeated string has no size bound](BUG-146-a-power-or-a-repeated-string-has-no-size-bound.md) | critical |  | L | high | config | PR-5 |
| [BUG-114 — Cyclopts cannot register subclasses that share a struct field name](BUG-114-cyclopts-cannot-register-subclasses-that-share-a-struct-field-name.md) | major |  | S | medium | behavior | PR-38 |
| [BUG-152 — A positional-only `__init__` parameter fails `build()` with a raw `TypeError`](BUG-152-a-positional-only-init-parameter-fails-build-with-a-raw-typeerror.md) | major |  | S | high | behavior | PR-5 |
| [BUG-156 — A positional-only parameter in a callable spec is passed by keyword](BUG-156-a-positional-only-parameter-in-a-callable-spec-is-passed-by-keyword.md) | major |  | S | high | behavior | PR-5 |
| [BUG-174 — An index delete on a dict writes the list-delete key into the dict](BUG-174-an-index-delete-on-a-dict-writes-the-list-delete-key.md) | major |  | S | medium | behavior | PR-5 |
| [BUG-117 — A union with an `Any` variant refuses to load and crashes `dump()`](BUG-117-a-union-with-an-any-variant-refuses-to-load-and-crashes-dump.md) | major |  | M | high | behavior | PR-5 |
| [BUG-145 — An expression that parses but nests past the recursion limit crashes the walkers](BUG-145-an-expression-that-parses-but-nests-past-the-recursion-limit-crashes-the-walkers.md) | major |  | M | high | behavior | PR-5 |
| [BUG-180 — Cyclopts refuses a flag whose name ends in a star](BUG-180-cyclopts-refuses-a-flag-whose-name-ends-in-a-star.md) | major |  | M | medium | behavior | PR-72 |
| [BUG-46 — The `90_integration` code blocks document an API that does not exist](BUG-46-old-help-blocks-document-a-removed-api.md) | minor |  | S | low | none | PR-13, PR-28 |
| [BUG-63 — A bare `--config` before `--help` shows help on argparse and errors on the other four](BUG-63-bare-config-before-help-shows-help-on-argparse.md) | minor |  | S | medium | behavior | PR-5 |
| [BUG-93 — Scalar cast flags stay refused on struct, collection and registered-leaf fields](BUG-93-scalar-cast-flags-stay-refused-on-struct-collection-and-leaf-fields.md) | minor |  | S | medium | behavior | PR-50 |
| [BUG-94 — Multi-variant unions refuse the scalar casts beyond the union's own scalars](BUG-94-multi-variant-unions-refuse-casts-beyond-their-own-scalars.md) | minor |  | S | medium | behavior | PR-50 |
| [BUG-98 — A dict-key delete with no base dict errors on the leaked `_DeleteSentinel`](BUG-98-a-dict-key-delete-with-no-base-dict-leaks-the-delete-sentinel.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-107 — A real field named like the tag, nested inside a union variant, is stripped by the type check](BUG-107-a-nested-real-field-named-like-the-tag-is-stripped-by-the-union-type-check.md) | minor |  | S | medium | behavior | PR-5 |
| [BUG-108 — A plain fixed tuple accepts the index spellings a namedtuple refuses](BUG-108-a-plain-fixed-tuple-accepts-the-index-spellings-a-namedtuple-refuses.md) | minor |  | S | medium | behavior | PR-5 |
| [BUG-109 — A namedtuple index patch ignores the field's default, where a tuple patch keeps it](BUG-109-a-namedtuple-index-patch-ignores-the-fields-default.md) | minor |  | S | medium | behavior | PR-39 |
| [BUG-110 — The walk accepts a path that continues past the union tag](BUG-110-the-walk-accepts-a-path-that-continues-past-the-tag.md) | minor |  | S | medium | behavior | PR-5 |
| [BUG-118 — `merge()`'s loading order names the env config pointer without its prefix](BUG-118-merge-docstring-names-the-env-config-pointer-without-its-prefix.md) | minor |  | S | low | behavior | PR-23 |
| [BUG-140 — The `from_namespace` / `from_context` docstrings still read the CLI channel out of the parse result](BUG-140-adapter-docstrings-read-the-cli-channel-out-of-the-parse-result.md) | minor |  | S | low | behavior | REF-72 |
| [BUG-142 — A namedtuple built from a dict accepts index keys the CLI refuses](BUG-142-a-namedtuple-built-from-a-dict-accepts-index-keys-the-cli-refuses.md) | minor |  | S | medium | config | PR-39, BUG-97 |
| [BUG-144 — The refusal of a method on a non-string reads "a int"](BUG-144-a-method-on-a-non-string-reads-a-int.md) | minor |  | S | low | behavior | BUG-122 |
| [BUG-153 — A class without its own `__init__` is a struct with `args` and `kwargs` fields](BUG-153-a-class-without-its-own-init-is-a-struct-with-args-and-kwargs-fields.md) | minor |  | S | high | config | PR-5 |
| [BUG-154 — An integer in a file is refused for a `float` field](BUG-154-an-integer-in-a-file-is-refused-for-a-float-field.md) | minor |  | S | high | behavior | PR-5 |
| [BUG-175 — A file's list-delete key holding no index list escapes as a raw TypeError](BUG-175-a-files-list-delete-key-holding-no-index-list-escapes-as-a-typeerror.md) | minor |  | S | low | none | PR-5, PR-9 |
| [BUG-176 — A bare optional fixed-arity flag gets a one-value usage line](BUG-176-a-bare-optional-fixed-arity-flag-gets-a-one-value-usage.md) | minor |  | S | low | behavior | PR-77 |
| [BUG-178 — A bare-prefix append is told it lacks the prefix](BUG-178-a-bare-prefix-append-is-told-it-lacks-the-prefix.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-183 — The bare prefix variable on a struct root is warned about as segment ''](BUG-183-the-bare-prefix-variable-on-a-struct-root-is-warned-about-as-segment-empty.md) | minor |  | S | low | none | PR-5 |
| [BUG-184 — A struct root that refuses an empty call escapes `build()` as a `TypeError`](BUG-184-a-struct-root-that-refuses-an-empty-call-escapes-build-as-a-typeerror.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | minor |  | M | low | behavior | PR-5, PR-13, PR-26 |
| [BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters](BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md) | minor |  | M | medium | behavior | PR-38 |
| [BUG-177 — A collection root's bare flag takes one token, which construction refuses](BUG-177-a-collection-roots-bare-flag-takes-one-token-construction-refuses.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-181 — An out-of-domain Literal or Enum flag exits with the framework's choice error on the adapters](BUG-181-an-out-of-domain-literal-or-enum-flag-exits-with-the-frameworks-choice-error.md) | minor |  | M | medium | behavior | PR-5, PR-13, PR-26 |
| [BUG-88 — A mount point below a direct root field has no `--config.<path>` entry](BUG-88-a-mount-point-below-a-direct-root-field-has-no-config-entry.md) | minor |  | L | medium | behavior | PR-13 |
| [BUG-119 — `_defaults.py` says four front-ends must agree; there are five](BUG-119-defaults-module-counts-four-front-ends.md) | trivial |  | S | low | none | BUG-7 |
| [BUG-149 — The testing protocol routes example tests to a folder that does not exist](BUG-149-the-testing-protocol-routes-example-tests-to-a-folder-that-does-not-exist.md) | trivial |  | S | low | none | BUG-52 |
| [BUG-150 — The protocols count four front-ends and leave typer out](BUG-150-the-protocols-count-four-front-ends-and-leave-typer-out.md) | trivial |  | S | low | none | BUG-7 |
| [BUG-151 — The namedtuple decision names the bugs board by its old file](BUG-151-the-namedtuple-decision-names-the-bugs-board-by-its-old-file.md) | trivial |  | S | low | none | PR-162 |

<!-- tickets:end -->

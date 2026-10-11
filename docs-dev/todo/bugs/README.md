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
| [BUG-182 — An env delete naming no member is dropped without a warning](BUG-182-an-env-delete-naming-no-member-is-dropped-without-a-warning.md) | critical |  | S | low | behavior | PR-5 |
| [BUG-186 — A root `json` cast swallows a field delete meant for the layers below](BUG-186-a-root-json-cast-swallows-a-field-delete-meant-for-the-layers-below.md) | critical |  | S | high | behavior | PR-87, BUG-3 |
| [BUG-193 — A closure or a lambda dumps as a path that cannot be imported](BUG-193-a-closure-dumps-as-a-path-that-cannot-be-imported.md) | critical (via BUG-191) |  | S | low | behavior | PR-5 |
| [BUG-190 — A typed `call:` spec merges with the lower layer's value instead of replacing it](BUG-190-a-typed-call-spec-merges-with-the-lower-layers-value.md) | critical |  | M | medium | behavior | FEAT-28 |
| [BUG-192 — A `class:` instance dumps the arguments it was built with, not the values it holds](BUG-192-a-class-instance-dumps-the-arguments-it-was-built-with.md) | critical |  | M | low | behavior | PR-5 |
| [BUG-146 — A power or a repeated string has no size bound](BUG-146-a-power-or-a-repeated-string-has-no-size-bound.md) | critical |  | L | high | config | PR-5 |
| [BUG-191 — A `call:` result on a Callable field dumps as the call, not as what it produced](BUG-191-a-call-result-on-a-callable-field-dumps-as-the-call.md) | critical | BUG-193 | S | low | behavior | PR-5 |
| [BUG-114 — Cyclopts cannot register subclasses that share a struct field name](BUG-114-cyclopts-cannot-register-subclasses-that-share-a-struct-field-name.md) | major |  | S | medium | behavior | PR-38 |
| [BUG-152 — A positional-only `__init__` parameter fails `build()` with a raw `TypeError`](BUG-152-a-positional-only-init-parameter-fails-build-with-a-raw-typeerror.md) | major |  | S | high | behavior | PR-5 |
| [BUG-156 — A positional-only parameter in a callable spec is passed by keyword](BUG-156-a-positional-only-parameter-in-a-callable-spec-is-passed-by-keyword.md) | major |  | S | high | behavior | PR-5 |
| [BUG-174 — An index delete on a dict writes the list-delete key into the dict](BUG-174-an-index-delete-on-a-dict-writes-the-list-delete-key.md) | major |  | S | medium | behavior | PR-5 |
| [BUG-202 — `dump_file` of a merged key delete escapes as a raw writer error](BUG-202-dump-file-of-a-merged-key-delete-escapes-as-a-raw-writer-error.md) | major |  | S | low | behavior | PR-5 |
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
| [BUG-176 — A bare optional fixed-arity flag gets a one-value usage line](BUG-176-a-bare-optional-fixed-arity-flag-gets-a-one-value-usage.md) | minor |  | S | low | behavior | PR-77 |
| [BUG-178 — A bare-prefix append is told it lacks the prefix](BUG-178-a-bare-prefix-append-is-told-it-lacks-the-prefix.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-183 — The bare prefix variable on a struct root is warned about as segment ''](BUG-183-the-bare-prefix-variable-on-a-struct-root-is-warned-about-as-segment-empty.md) | minor |  | S | low | none | PR-5 |
| [BUG-184 — A struct root that refuses an empty call escapes `build()` as a `TypeError`](BUG-184-a-struct-root-that-refuses-an-empty-call-escapes-build-as-a-typeerror.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-187 — A bare `dict` annotation is refused as an unsupported leaf](BUG-187-a-bare-dict-annotation-is-refused-as-an-unsupported-leaf.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-188 — A class key on a scalar field is refused as a coercion error](BUG-188-a-class-key-on-a-scalar-field-is-refused-as-a-coercion-error.md) | minor |  | S | low | behavior | unknown |
| [BUG-195 — A builtin method descriptor loads from its path but cannot be dumped](BUG-195-a-builtin-method-descriptor-cannot-be-dumped.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-196 — A class refusal on a typed field points to a `call:` that is refused too](BUG-196-a-class-refusal-points-to-a-call-that-is-refused-too.md) | minor |  | S | low | behavior | FEAT-29 |
| [BUG-197 — A typed call's opener flag is described as a value, not as the function to call](BUG-197-a-typed-calls-opener-flag-is-described-as-a-spec-value.md) | minor |  | S | low | behavior | FEAT-32 |
| [BUG-198 — A fixed-arity element flag takes one token on click and typer](BUG-198-a-fixed-arity-element-flag-takes-one-token-on-click-and-typer.md) | minor |  | S | low | config | PR-72 |
| [BUG-200 — A name patch over a union's list fails naming the merge's own `__base__` shape](BUG-200-a-name-patch-over-a-unions-list-fails-naming-the-merges-own-shape.md) | minor |  | S | low | none | BUG-160 |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | minor |  | M | low | behavior | PR-5, PR-13, PR-26, BUG-179 |
| [BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters](BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md) | minor |  | M | medium | behavior | PR-38 |
| [BUG-177 — A collection root's bare flag takes one token, which construction refuses](BUG-177-a-collection-roots-bare-flag-takes-one-token-construction-refuses.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-181 — An out-of-domain Literal or Enum flag exits with the framework's choice error on the adapters](BUG-181-an-out-of-domain-literal-or-enum-flag-exits-with-the-frameworks-choice-error.md) | minor |  | M | medium | behavior | PR-5, PR-13, PR-26 |
| [BUG-194 — A `bind:` keyword built as a struct dumps as the instance, which no file format writes](BUG-194-a-bind-keyword-built-as-a-struct-dumps-as-the-instance.md) | minor |  | M | low | behavior | PR-93 |
| [BUG-88 — A mount point below a direct root field has no `--config.<path>` entry](BUG-88-a-mount-point-below-a-direct-root-field-has-no-config-entry.md) | minor |  | L | medium | behavior | PR-13 |
| [BUG-201 — An environment variable below a dict appends, though the environment has no append](BUG-201-an-environment-variable-below-a-dict-appends-though-the-environment-has-no-append.md) | minor | FEAT-18 | S | medium | config | PR-5 |
| [BUG-119 — `_defaults.py` says four front-ends must agree; there are five](BUG-119-defaults-module-counts-four-front-ends.md) | trivial |  | S | low | none | BUG-7 |
| [BUG-149 — The testing protocol routes example tests to a folder that does not exist](BUG-149-the-testing-protocol-routes-example-tests-to-a-folder-that-does-not-exist.md) | trivial |  | S | low | none | BUG-52 |
| [BUG-204 — Docstrings outside `_defaults.py` and an open ticket count four front-ends](BUG-204-docstrings-outside-defaults-count-four-front-ends.md) | trivial |  | S | low | none | BUG-7 |

<!-- tickets:end -->

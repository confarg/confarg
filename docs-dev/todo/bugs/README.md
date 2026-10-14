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
| [BUG-146 — A power or a repeated string has no size bound](BUG-146-a-power-or-a-repeated-string-has-no-size-bound.md) | critical |  | L | high | config | PR-5 |
| [BUG-228 — A JSON cast's `key-` shorthand deletes below only in some positions](BUG-228-a-json-casts-delete-shorthand-deletes-below-only-in-some-positions.md) | critical | Q-7 | S | high | behavior | PR-87, BUG-3 |
| [BUG-114 — Cyclopts cannot register subclasses that share a struct field name](BUG-114-cyclopts-cannot-register-subclasses-that-share-a-struct-field-name.md) | major |  | S | medium | behavior | PR-38 |
| [BUG-174 — An index delete on a dict writes the list-delete key into the dict](BUG-174-an-index-delete-on-a-dict-writes-the-list-delete-key.md) | major |  | S | medium | behavior | PR-5 |
| [BUG-202 — `dump_file` of a merged key delete escapes as a raw writer error](BUG-202-dump-file-of-a-merged-key-delete-escapes-as-a-raw-writer-error.md) | major |  | S | low | behavior | PR-5 |
| [BUG-230 — A `type[X]` field refuses the dotted path a file holds, so its own dump does not load](BUG-230-a-type-field-refuses-the-dotted-path-a-file-holds.md) | major |  | S | medium | behavior | PR-5 |
| [BUG-145 — An expression that parses but nests past the recursion limit crashes the walkers](BUG-145-an-expression-that-parses-but-nests-past-the-recursion-limit-crashes-the-walkers.md) | major |  | M | high | behavior | PR-5 |
| [BUG-180 — Cyclopts refuses a flag whose name ends in a star](BUG-180-cyclopts-refuses-a-flag-whose-name-ends-in-a-star.md) | major |  | M | medium | behavior | PR-72 |
| [BUG-219 — A fragment appended to a list loses its `locals`](BUG-219-a-fragment-appended-to-a-list-loses-its-locals.md) | major |  | M | high | behavior | PR-105 |
| [BUG-233 — The CLI refuses a nested spec below a `class:` constructor argument](BUG-233-the-cli-refuses-a-nested-spec-below-a-class-constructor-argument.md) | major |  | M | medium | behavior | PR-11 |
| [BUG-234 — A Callable beside another union variant is never built from a spec](BUG-234-a-callable-beside-another-union-variant-is-never-built-from-a-spec.md) | major |  | M | medium | behavior | PR-5 |
| [BUG-98 — A dict-key delete with no base dict errors on the leaked `_DeleteSentinel`](BUG-98-a-dict-key-delete-with-no-base-dict-leaks-the-delete-sentinel.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-108 — A plain fixed tuple accepts the index spellings a namedtuple refuses](BUG-108-a-plain-fixed-tuple-accepts-the-index-spellings-a-namedtuple-refuses.md) | minor |  | S | medium | behavior | PR-5 |
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
| [BUG-195 — A builtin method descriptor loads from its path but cannot be dumped](BUG-195-a-builtin-method-descriptor-cannot-be-dumped.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-197 — A typed call's opener flag is described as a value, not as the function to call](BUG-197-a-typed-calls-opener-flag-is-described-as-a-spec-value.md) | minor |  | S | low | behavior | FEAT-32 |
| [BUG-198 — A fixed-arity element flag takes one token on click and typer](BUG-198-a-fixed-arity-element-flag-takes-one-token-on-click-and-typer.md) | minor |  | S | low | config | PR-72 |
| [BUG-222 — A registered `NewType` crashes with a raw `TypeError`](BUG-222-a-registered-newtype-crashes-with-a-raw-typeerror.md) | minor |  | S | medium | behavior | PR-37 |
| [BUG-235 — A union tag that is no string escapes `build()` as a raw `AttributeError`](BUG-235-a-tag-that-is-no-string-escapes-as-a-raw-attributeerror.md) | minor |  | S | medium | behavior | PR-5 |
| [BUG-239 — A cast pin below a dict is merged into it](BUG-239-a-cast-pin-below-a-dict-is-merged-into-it.md) | minor |  | S | low | behavior | PR-50 |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | minor |  | M | low | behavior | PR-5, PR-13, PR-26, BUG-179 |
| [BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters](BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md) | minor |  | M | medium | behavior | PR-38 |
| [BUG-177 — A collection root's bare flag takes one token, which construction refuses](BUG-177-a-collection-roots-bare-flag-takes-one-token-construction-refuses.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-181 — An out-of-domain Literal or Enum flag exits with the framework's choice error on the adapters](BUG-181-an-out-of-domain-literal-or-enum-flag-exits-with-the-frameworks-choice-error.md) | minor |  | M | medium | behavior | PR-5, PR-13, PR-26 |
| [BUG-194 — A `bind:` keyword built as a struct dumps as the instance, which no file format writes](BUG-194-a-bind-keyword-built-as-a-struct-dumps-as-the-instance.md) | minor |  | M | low | behavior | PR-93 |
| [BUG-220 — A reference into a list with pending ops reads none of its items](BUG-220-a-reference-into-a-list-with-pending-ops-reads-none-of-its-items.md) | minor |  | M | high | behavior | PR-5 |
| [BUG-225 — argparse completion offers nothing below a tagged class that holds itself](BUG-225-argparse-completion-offers-nothing-below-a-tagged-class-that-holds-itself.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-236 — A list argument of a class named below a Callable or an `Any` takes one token](BUG-236-a-list-argument-of-a-class-named-below-a-callable-takes-one-token.md) | minor |  | M | high | behavior | PR-5 |
| [BUG-240 — A `*args` parameter cannot be set under the `args` of `bind:` or `call:`](BUG-240-a-var-positional-parameter-cannot-be-set-under-args.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-201 — An environment variable below a dict appends, though the environment has no append](BUG-201-an-environment-variable-below-a-dict-appends-though-the-environment-has-no-append.md) | minor | FEAT-18 | S | medium | config | PR-5 |
| [BUG-149 — The testing protocol routes example tests to a folder that does not exist](BUG-149-the-testing-protocol-routes-example-tests-to-a-folder-that-does-not-exist.md) | trivial |  | S | low | none | BUG-52 |

<!-- tickets:end -->

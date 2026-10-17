# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from the documented intent.
One ticket per file; see [../README.md](../README.md) for the format, including the [reproduction](../README.md#reproduction) every entry here carries.

Cross-channel parity is mandatory ([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)), so a parity entry here is a violation nobody has approved, not a design choice.

<!-- tickets:start -->

| Ticket | Severity | Blocked by | Effort | Risk | Impact | Introduced by |
|---|---|---|---|---|---|---|
| [BUG-180 — Cyclopts refuses a flag whose name ends in a star](BUG-180-cyclopts-refuses-a-flag-whose-name-ends-in-a-star.md) | major |  | M | medium | behavior | PR-72 |
| [BUG-219 — A fragment appended to a list loses its `locals`](BUG-219-a-fragment-appended-to-a-list-loses-its-locals.md) | major |  | M | high | behavior | PR-105 |
| [BUG-253 — A dict subclass reads as a struct of its constructor's parameters](BUG-253-a-dict-subclass-reads-as-a-struct-of-its-constructors-parameters.md) | major |  | M | high | config | PR-5 |
| [BUG-248 — Data nested a few hundred levels deep crashes the walkers](BUG-248-data-nested-a-few-hundred-levels-deep-crashes-the-walkers.md) | major |  | L | high | behavior | PR-5 |
| [BUG-118 — `merge()`'s loading order names the env config pointer without its prefix](BUG-118-merge-docstring-names-the-env-config-pointer-without-its-prefix.md) | minor |  | S | low | behavior | PR-23 |
| [BUG-140 — The `from_namespace` / `from_context` docstrings still read the CLI channel out of the parse result](BUG-140-adapter-docstrings-read-the-cli-channel-out-of-the-parse-result.md) | minor |  | S | low | behavior | REF-72 |
| [BUG-154 — An integer in a file is refused for a `float` field](BUG-154-an-integer-in-a-file-is-refused-for-a-float-field.md) | minor |  | S | high | behavior | PR-5 |
| [BUG-176 — A bare optional fixed-arity flag gets a one-value usage line](BUG-176-a-bare-optional-fixed-arity-flag-gets-a-one-value-usage.md) | minor |  | S | low | behavior | PR-77 |
| [BUG-178 — A bare-prefix append is told it lacks the prefix](BUG-178-a-bare-prefix-append-is-told-it-lacks-the-prefix.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-183 — The bare prefix variable on a struct root is warned about as segment ''](BUG-183-the-bare-prefix-variable-on-a-struct-root-is-warned-about-as-segment-empty.md) | minor |  | S | low | none | PR-5 |
| [BUG-195 — A builtin method descriptor loads from its path but cannot be dumped](BUG-195-a-builtin-method-descriptor-cannot-be-dumped.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-197 — A typed call's opener flag is described as a value, not as the function to call](BUG-197-a-typed-calls-opener-flag-is-described-as-a-spec-value.md) | minor |  | S | low | behavior | FEAT-32 |
| [BUG-198 — A fixed-arity element flag takes one token on click and typer](BUG-198-a-fixed-arity-element-flag-takes-one-token-on-click-and-typer.md) | minor |  | S | low | config | PR-72 |
| [BUG-222 — A registered `NewType` crashes with a raw `TypeError`](BUG-222-a-registered-newtype-crashes-with-a-raw-typeerror.md) | minor |  | S | medium | behavior | PR-37 |
| [BUG-235 — A union tag that is no string escapes `build()` as a raw `AttributeError`](BUG-235-a-tag-that-is-no-string-escapes-as-a-raw-attributeerror.md) | minor |  | S | medium | behavior | PR-5 |
| [BUG-242 — A lone `__root__` in a root configuration file is unwrapped as a fragment's](BUG-242-a-lone-root-key-in-a-root-file-is-unwrapped-as-a-fragments.md) | minor |  | S | low | behavior | PR-209 |
| [BUG-245 — Dumping a non-string key to TOML or JSON escapes as a raw `TypeError`](BUG-245-dumping-a-non-string-key-to-toml-or-json-escapes-as-a-raw-typeerror.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-247 — A decimal signal fails an expression with a list of classes](BUG-247-a-decimal-signal-fails-an-expression-with-a-list-of-classes.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-250 — A Callable in a union does not advertise its openers](BUG-250-a-callable-in-a-union-does-not-advertise-its-openers.md) | minor |  | S | medium | behavior | PR-13 |
| [BUG-251 — An object no configuration spells fails in the file writer, with the writer's own error](BUG-251-an-object-no-configuration-spells-fails-in-the-file-writer.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-252 — A class tag on a union with no struct variant lists no candidate](BUG-252-a-class-tag-on-a-union-with-no-struct-variant-lists-no-candidate.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | minor |  | M | low | behavior | PR-5, PR-13, PR-26, BUG-179 |
| [BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters](BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md) | minor |  | M | medium | behavior | PR-38 |
| [BUG-177 — A collection root's bare flag takes one token, which construction refuses](BUG-177-a-collection-roots-bare-flag-takes-one-token-construction-refuses.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-181 — An out-of-domain Literal or Enum flag exits with the framework's choice error on the adapters](BUG-181-an-out-of-domain-literal-or-enum-flag-exits-with-the-frameworks-choice-error.md) | minor |  | M | medium | behavior | PR-5, PR-13, PR-26 |
| [BUG-194 — A `bind:` keyword built as a struct dumps as the instance, which no file format writes](BUG-194-a-bind-keyword-built-as-a-struct-dumps-as-the-instance.md) | minor |  | M | low | behavior | PR-93 |
| [BUG-220 — A reference into a list with pending ops reads none of its items](BUG-220-a-reference-into-a-list-with-pending-ops-reads-none-of-its-items.md) | minor |  | M | high | behavior | PR-5 |
| [BUG-225 — argparse completion offers nothing below a tagged class that holds itself](BUG-225-argparse-completion-offers-nothing-below-a-tagged-class-that-holds-itself.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-240 — A `*args` parameter cannot be set under the `args` of `bind:` or `call:`](BUG-240-a-var-positional-parameter-cannot-be-set-under-args.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-149 — The testing protocol routes example tests to a folder that does not exist](BUG-149-the-testing-protocol-routes-example-tests-to-a-folder-that-does-not-exist.md) | trivial |  | S | low | none | BUG-52 |
| [BUG-249 — The YAML formatter strips quotes the YAML loader needs](BUG-249-the-yaml-formatter-strips-quotes-the-loader-needs.md) | trivial |  | S | low | none | PR-61 |

<!-- tickets:end -->

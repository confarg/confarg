# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from the documented intent.
One ticket per file; see [../README.md](../README.md) for the format, including the [reproduction](../README.md#reproduction) every entry here carries.

Cross-channel parity is mandatory ([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)), so a parity entry here is a violation nobody has approved, not a design choice.

<!-- tickets:start -->

| Ticket | Severity | Blocked by | Effort | Risk | Impact | Introduced by |
|---|---|---|---|---|---|---|
| [BUG-298 — A union without `None` takes a file's `null`](BUG-298-a-union-without-none-takes-a-files-null.md) | critical |  | S | medium | config | PR-11 |
| [BUG-283 — A reference to a registered leaf written as a tagged dict reads the dict](BUG-283-a-reference-to-a-tagged-registered-leaf-reads-its-dict.md) | critical |  | M | high | config | BUG-16, BUG-246 |
| [BUG-288 — An ambiguity inside a union variant lets the next variant take the value](BUG-288-an-ambiguity-inside-a-union-variant-lets-the-next-variant-take-the-value.md) | critical |  | M | high | config | PR-5 |
| [BUG-295 — A union offers an untagged value to a variant that demands its tag](BUG-295-a-union-offers-an-untagged-value-to-a-variant-that-demands-its-tag.md) | major (via FEAT-57) |  | M | high | config | PR-63 |
| [BUG-300 — A tag matching variants of two classes is refused as ambiguous](BUG-300-a-tag-matching-variants-of-two-classes-is-refused-as-ambiguous.md) | major |  | M | high | behavior | PR-5, FEAT-13 |
| [BUG-118 — `merge()`'s loading order names the env config pointer without its prefix](BUG-118-merge-docstring-names-the-env-config-pointer-without-its-prefix.md) | minor |  | S | low | behavior | PR-23 |
| [BUG-140 — The `from_namespace` / `from_context` docstrings still read the CLI channel out of the parse result](BUG-140-adapter-docstrings-read-the-cli-channel-out-of-the-parse-result.md) | minor |  | S | low | behavior | REF-72 |
| [BUG-176 — A bare optional fixed-arity flag gets a one-value usage line](BUG-176-a-bare-optional-fixed-arity-flag-gets-a-one-value-usage.md) | minor |  | S | low | behavior | PR-77 |
| [BUG-281 — A method a module publishes off its own instance does not dump as its path](BUG-281-a-method-a-module-publishes-off-its-own-instance-does-not-dump-as-its-path.md) | minor |  | S | medium | behavior | PR-5 |
| [BUG-282 — A lazy module hook that raises on `__all__` escapes `dotted_name`](BUG-282-a-lazy-module-hook-raising-on-all-escapes-dotted-name.md) | minor |  | S | low | none | BUG-279 |
| [BUG-285 — A shadowed-tag warning at a struct root names the key `__root__`](BUG-285-a-shadowed-tag-warning-at-a-struct-root-names-the-key-root.md) | minor |  | S | medium | behavior | PR-264 |
| [BUG-287 — An append at the top of a root file for a list-or-struct union crashes](BUG-287-an-append-at-the-top-of-a-root-file-for-a-list-or-struct-union-crashes.md) | minor |  | S | medium | behavior | PR-458 |
| [BUG-289 — A refused dict key reads as the value](BUG-289-a-refused-dict-key-reads-as-the-value.md) | minor |  | S | medium | behavior | PR-5 |
| [BUG-292 — A help group is headed by a docstring its class inherits](BUG-292-a-help-group-is-headed-by-a-docstring-its-class-inherits.md) | minor |  | S | low | behavior | PR-13 |
| [BUG-299 — A union with a struct variant registers no cast flag](BUG-299-a-union-with-a-struct-variant-registers-no-cast-flag.md) | minor |  | S | medium | behavior | PR-54 |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | minor |  | M | low | behavior | PR-5, PR-13, PR-26, BUG-179 |
| [BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters](BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md) | minor |  | M | medium | behavior | PR-38 |
| [BUG-181 — An out-of-domain Literal or Enum flag exits with the framework's choice error on the adapters](BUG-181-an-out-of-domain-literal-or-enum-flag-exits-with-the-frameworks-choice-error.md) | minor |  | M | medium | behavior | PR-5, PR-13, PR-26 |
| [BUG-194 — A `bind:` keyword built as a struct dumps as the instance, which no file format writes](BUG-194-a-bind-keyword-built-as-a-struct-dumps-as-the-instance.md) | minor |  | M | low | behavior | PR-93 |
| [BUG-225 — argparse completion offers nothing below a tagged class that holds itself](BUG-225-argparse-completion-offers-nothing-below-a-tagged-class-that-holds-itself.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-240 — A `*args` parameter cannot be set under the `args` of `bind:` or `call:`](BUG-240-a-var-positional-parameter-cannot-be-set-under-args.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-257 — A lone expression token on a list flag is one item, where the environment reads it as the whole list](BUG-257-a-lone-expression-token-on-a-list-flag-is-one-item.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-286 — A `class` flag on a type no tag selects imports its value from argv](BUG-286-a-class-flag-on-a-type-no-tag-selects-imports-its-value-from-argv.md) | minor |  | M | medium | behavior | BUG-6 |
| [BUG-290 — A refusal at the root names its position as the empty string](BUG-290-a-refusal-at-the-root-names-its-position-as-the-empty-string.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-269 — A constructor's own exception escapes construction raw, with no path](BUG-269-a-constructors-own-exception-escapes-construction-raw.md) | minor |  | L | high | api | PR-5 |
| [BUG-149 — The testing protocol routes example tests to a folder that does not exist](BUG-149-the-testing-protocol-routes-example-tests-to-a-folder-that-does-not-exist.md) | trivial |  | S | low | none | BUG-52 |
| [BUG-249 — The YAML formatter strips quotes the YAML loader needs](BUG-249-the-yaml-formatter-strips-quotes-the-loader-needs.md) | trivial |  | S | low | none | PR-61 |

<!-- tickets:end -->

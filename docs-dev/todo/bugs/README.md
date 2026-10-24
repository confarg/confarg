# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from the documented intent.
One ticket per file; see [../README.md](../README.md) for the format, including the [reproduction](../README.md#reproduction) every entry here carries.

Cross-channel parity is mandatory ([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)), so a parity entry here is a violation nobody has approved, not a design choice.

<!-- tickets:start -->

| Ticket | Severity | Blocked by | Effort | Risk | Impact | Introduced by |
|---|---|---|---|---|---|---|
| [BUG-118 — `merge()`'s loading order names the env config pointer without its prefix](BUG-118-merge-docstring-names-the-env-config-pointer-without-its-prefix.md) | minor |  | S | low | behavior | PR-23 |
| [BUG-140 — The `from_namespace` / `from_context` docstrings still read the CLI channel out of the parse result](BUG-140-adapter-docstrings-read-the-cli-channel-out-of-the-parse-result.md) | minor |  | S | low | behavior | REF-72 |
| [BUG-176 — A bare optional fixed-arity flag gets a one-value usage line](BUG-176-a-bare-optional-fixed-arity-flag-gets-a-one-value-usage.md) | minor |  | S | low | behavior | PR-77 |
| [BUG-195 — A builtin method descriptor loads from its path but cannot be dumped](BUG-195-a-builtin-method-descriptor-cannot-be-dumped.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-242 — A lone `__root__` in a root configuration file is unwrapped as a fragment's](BUG-242-a-lone-root-key-in-a-root-file-is-unwrapped-as-a-fragments.md) | minor |  | S | low | behavior | PR-209 |
| [BUG-252 — A class tag on a union with no struct variant lists no candidate](BUG-252-a-class-tag-on-a-union-with-no-struct-variant-lists-no-candidate.md) | minor |  | S | low | behavior | PR-5 |
| [BUG-256 — A module that fails while imported is named by the path being tried, not by the module](BUG-256-a-module-that-fails-is-named-by-the-path-tried.md) | minor |  | S | low | none | PR-22 |
| [BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) | minor |  | M | low | behavior | PR-5, PR-13, PR-26, BUG-179 |
| [BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters](BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md) | minor |  | M | medium | behavior | PR-38 |
| [BUG-181 — An out-of-domain Literal or Enum flag exits with the framework's choice error on the adapters](BUG-181-an-out-of-domain-literal-or-enum-flag-exits-with-the-frameworks-choice-error.md) | minor |  | M | medium | behavior | PR-5, PR-13, PR-26 |
| [BUG-194 — A `bind:` keyword built as a struct dumps as the instance, which no file format writes](BUG-194-a-bind-keyword-built-as-a-struct-dumps-as-the-instance.md) | minor |  | M | low | behavior | PR-93 |
| [BUG-225 — argparse completion offers nothing below a tagged class that holds itself](BUG-225-argparse-completion-offers-nothing-below-a-tagged-class-that-holds-itself.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-240 — A `*args` parameter cannot be set under the `args` of `bind:` or `call:`](BUG-240-a-var-positional-parameter-cannot-be-set-under-args.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-257 — A lone expression token on a list flag is one item, where the environment reads it as the whole list](BUG-257-a-lone-expression-token-on-a-list-flag-is-one-item.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-261 — A dict keyed by a union refuses every key](BUG-261-a-dict-keyed-by-a-union-refuses-every-key.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-266 — A root union's scalar variant has no spelling in any channel](BUG-266-a-root-unions-scalar-variant-has-no-spelling.md) | minor |  | M | medium | behavior | PR-5 |
| [BUG-269 — A constructor's own exception escapes construction raw, with no path](BUG-269-a-constructors-own-exception-escapes-construction-raw.md) | minor |  | L | high | api | PR-5 |
| [BUG-149 — The testing protocol routes example tests to a folder that does not exist](BUG-149-the-testing-protocol-routes-example-tests-to-a-folder-that-does-not-exist.md) | trivial |  | S | low | none | BUG-52 |
| [BUG-249 — The YAML formatter strips quotes the YAML loader needs](BUG-249-the-yaml-formatter-strips-quotes-the-loader-needs.md) | trivial |  | S | low | none | PR-61 |

<!-- tickets:end -->

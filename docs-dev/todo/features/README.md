# Features

Missing behavior worth having, and ideas not yet vetted. One ticket per file; see
[../README.md](../README.md) for the format. Anything accepted or rejected here leaves a
decision in
[../../architecture/design-decisions/README.md](../../architecture/design-decisions/README.md).

An entry carrying `needs_design: true` is an unvetted idea: it has no design yet, so deciding
whether to do it at all is the next actionable step, and its effort sizes that decision.

<!-- tickets:start -->

| Ticket | Severity | Blocked by | Effort | Risk | Impact |
|---|---|---|---|---|---|
| [FEAT-14 — Dataclass fields that are not `__init__` parameters](FEAT-14-dataclass-fields-outside-init.md) | major |  | L | high | behavior |
| [FEAT-42 — An `Any` field reads callable specs and dumps an object as the spec that rebuilds it](FEAT-42-an-any-field-reads-callable-specs.md) | major |  | L | high | config |
| [FEAT-5 — Optional structural validation right after `merge()`](FEAT-5-structural-validation-after-merge.md) | minor |  | S | low | behavior |
| [FEAT-7 — Lazy resolution between `merge` and `build`](FEAT-7-lazy-resolution-merge-to-build.md) | minor |  | M | high | behavior |
| [FEAT-8 — Value provenance](FEAT-8-value-provenance.md) | minor |  | M | high | behavior |
| [FEAT-15 — No way to inspect the flags of a class the tag has not named yet](FEAT-15-inspect-flags-of-unnamed-class.md) | minor |  | M | low | behavior |
| [FEAT-16 — Let `__cast__` name a leaf type by dotted path](FEAT-16-dotted-cast-names.md) | minor |  | M | medium | behavior |
| [FEAT-17 — An end-of-options separator (`--`)](FEAT-17-end-of-options-separator.md) | minor |  | M | medium | behavior |
| [FEAT-18 — The environment channel has no append spelling](FEAT-18-no-append-spelling-in-the-environment.md) | minor |  | M | low | behavior |
| [FEAT-24 — Writing a configuration back to a URL](FEAT-24-writing-a-configuration-to-a-url.md) | minor |  | M | low | behavior |
| [FEAT-38 — A `default_factory` default is no base layer](FEAT-38-a-factory-default-is-no-base.md) | minor |  | M | medium | behavior |
| [FEAT-40 — A field accepts a wider input than the type it holds](FEAT-40-a-field-accepts-a-wider-input-than-it-holds.md) | minor |  | M | high | behavior |
| [FEAT-41 — A tyro adapter](FEAT-41-a-tyro-adapter.md) | minor |  | M | medium | behavior |
| [FEAT-1 — Uneven shell-completion coverage](FEAT-1-uneven-shell-completion-coverage.md) | minor |  | L | low | behavior |
| [FEAT-2 — Protocol-typed callables and `**kwargs`](FEAT-2-protocol-callables-and-kwargs.md) | minor |  | L | medium | behavior |
| [FEAT-6 — `Annotated` field metadata read by all three channels](FEAT-6-annotated-field-metadata.md) | minor |  | L | medium | behavior |
| [FEAT-9 — A `confarg check` command to validate a configuration against a target](FEAT-9-confarg-check-command.md) | minor |  | L | low | behavior |
| [FEAT-12 — Carefully scoped expression expansion](FEAT-12-scoped-expression-expansion.md) | minor |  | L | high | behavior |
| [FEAT-13 — Struct types that are generic](FEAT-13-generic-struct-types.md) | minor |  | L | high | behavior |
| [FEAT-19 — App-declared defaults, mounted at the type that declares them](FEAT-19-app-declared-defaults.md) | minor |  | L | medium | behavior |
| [FEAT-21 — Expression functions supplied by the application](FEAT-21-app-supplied-expression-functions.md) | minor |  | L | high | behavior |
| [FEAT-22 — The process environment as an expression namespace](FEAT-22-environment-namespace-in-expressions.md) | minor |  | L | high | behavior |
| [FEAT-35 — Let `${...}` read a `call:` result](FEAT-35-expressions-read-call-results.md) | minor |  | L | high | behavior |
| [FEAT-23 — A post-resolve transform layer](FEAT-23-post-resolve-transform-layer.md) | minor |  | XL | high | config |
| [FEAT-20 — Derived values that cannot be made inconsistent](FEAT-20-enforced-derived-values.md) | minor | FEAT-19 | M | medium | behavior |
| [FEAT-39 — A struct instance default is no base layer](FEAT-39-a-struct-instance-default-is-no-base.md) | minor | FEAT-38 | M | medium | none |
| [FEAT-10 — A `confarg explain` command showing the final configuration and each value's origin](FEAT-10-confarg-explain-command.md) | minor | FEAT-8 | XL | low | behavior |
| [FEAT-4 — An explicit ordered patch-op stream](FEAT-4-ordered-patch-op-stream.md) | trivial |  | M | high | none |

<!-- tickets:end -->

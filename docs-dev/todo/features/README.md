# Features

Missing behavior worth having, and ideas not yet vetted.
One ticket per file; see [../README.md](../README.md) for the format.
Anything accepted or rejected here leaves a decision in [../../architecture/design-decisions/README.md](../../architecture/design-decisions/README.md).

An entry carrying `needs_design: true` is an unvetted idea: it has no design yet, so deciding whether to do it at all is the next actionable step, and its effort sizes that decision.

<!-- tickets:start -->

| Ticket | Severity | Blocked by | Effort | Risk | Impact |
|---|---|---|---|---|---|
| [FEAT-5 — Optional structural validation right after `merge()`](FEAT-5-structural-validation-after-merge.md) | minor |  | S | low | behavior |
| [FEAT-26 — The expression whitelist is not documented for users](FEAT-26-the-expression-whitelist-is-not-documented-for-users.md) | minor |  | S | low | none |
| [FEAT-7 — Lazy resolution between `merge` and `build`](FEAT-7-lazy-resolution-merge-to-build.md) | minor |  | M | high | behavior |
| [FEAT-8 — Value provenance](FEAT-8-value-provenance.md) | minor |  | M | high | behavior |
| [FEAT-15 — No way to inspect the flags of a class the tag has not named yet](FEAT-15-inspect-flags-of-unnamed-class.md) | minor |  | M | low | behavior |
| [FEAT-16 — Let `__cast__` name a leaf type by dotted path](FEAT-16-dotted-cast-names.md) | minor |  | M | medium | behavior |
| [FEAT-17 — An end-of-options separator (`--`)](FEAT-17-end-of-options-separator.md) | minor |  | M | medium | behavior |
| [FEAT-24 — Writing a configuration back to a URL](FEAT-24-writing-a-configuration-to-a-url.md) | minor |  | M | low | behavior |
| [FEAT-38 — A `default_factory` default is no base layer](FEAT-38-a-factory-default-is-no-base.md) | minor |  | M | medium | behavior |
| [FEAT-40 — A field accepts a wider input than the type it holds](FEAT-40-a-field-accepts-a-wider-input-than-it-holds.md) | minor |  | M | high | behavior |
| [FEAT-41 — A tyro adapter](FEAT-41-a-tyro-adapter.md) | minor |  | M | medium | behavior |
| [FEAT-46 — A union's refusal names each variant's reason](FEAT-46-a-union-refusal-names-each-variants-reason.md) | minor |  | M | low | behavior |
| [FEAT-48 — A resolved dictionary that replays a run](FEAT-48-a-resolved-dictionary-that-replays-a-run.md) | minor |  | M | medium | behavior |
| [FEAT-49 — Registering how a class dumps](FEAT-49-registering-how-a-class-dumps.md) | minor |  | M | medium | behavior |
| [FEAT-50 — A `**kwargs` forwarded to the parent sets the parent's members](FEAT-50-a-kwargs-forwarded-to-the-parent-sets-its-members.md) | minor |  | M | high | config |
| [FEAT-52 — A file's float literal that overflows reads as `inf` silently](FEAT-52-a-file-float-literal-that-overflows-reads-as-inf-silently.md) | minor |  | M | medium | behavior |
| [FEAT-53 — A `collections.abc` implementer reads as a struct](FEAT-53-a-collections-abc-implementer-reads-as-a-struct.md) | minor |  | M | medium | config |
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
| [FEAT-45 — `TypedDict` fields](FEAT-45-typeddict-fields.md) | minor |  | L | high | behavior |
| [FEAT-47 — A confarg object holding the target and its sources](FEAT-47-a-confarg-object-holding-the-target-and-its-sources.md) | minor |  | L | low | behavior |
| [FEAT-23 — A post-resolve transform layer](FEAT-23-post-resolve-transform-layer.md) | minor |  | XL | high | config |
| [FEAT-20 — Derived values that cannot be made inconsistent](FEAT-20-enforced-derived-values.md) | minor | FEAT-19 | M | medium | behavior |
| [FEAT-39 — A struct instance default is no base layer](FEAT-39-a-struct-instance-default-is-no-base.md) | minor | FEAT-38 | M | medium | none |
| [FEAT-10 — A `confarg explain` command showing the final configuration and each value's origin](FEAT-10-confarg-explain-command.md) | minor | FEAT-8 | XL | low | behavior |
| [FEAT-4 — An explicit ordered patch-op stream](FEAT-4-ordered-patch-op-stream.md) | trivial |  | M | high | none |
| [FEAT-44 — YAML tags for a file's merge ops](FEAT-44-yaml-tags-for-a-files-merge-ops.md) | trivial |  | M | medium | none |

<!-- tickets:end -->

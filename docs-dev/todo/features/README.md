# Features

Missing behavior worth having, and ideas not yet vetted. One ticket per file; see
[../README.md](../README.md) for the format. Anything accepted or rejected here leaves a
decision in
[../../architecture/10-design-decisions.md](../../architecture/10-design-decisions.md).

An entry whose effort reads *(design pass; implementation not sized)* is an unvetted idea: it
has no design yet, so deciding whether to do it at all is the next actionable step.

<!-- tickets:start -->

| Ticket | Effort | Risk | Impact |
|---|---|---|---|
| [FEAT-1 — Uneven shell-completion coverage](FEAT-1-uneven-shell-completion-coverage.md) | L | low | behavior |
| [FEAT-2 — Protocol-typed callables and `**kwargs`](FEAT-2-protocol-callables-and-kwargs.md) | L | medium | behavior |
| [FEAT-3 — A registry of reserved sentinel keys](FEAT-3-reserved-sentinel-key-registry.md) | S | high | config |
| [FEAT-4 — An explicit ordered patch-op stream](FEAT-4-ordered-patch-op-stream.md) | M | high | none |
| [FEAT-5 — Optional structural validation right after `merge()`](FEAT-5-structural-validation-after-merge.md) | S | low | behavior |
| [FEAT-6 — `Annotated` field metadata read by all three channels](FEAT-6-annotated-field-metadata.md) | L | medium | behavior |
| [FEAT-7 — Lazy resolution between `merge` and `build`](FEAT-7-lazy-resolution-merge-to-build.md) | M | high | behavior |
| [FEAT-8 — Value provenance](FEAT-8-value-provenance.md) | M | high | behavior |
| [FEAT-9 — A `confarg check` command to validate a configuration against a target](FEAT-9-confarg-check-command.md) | L | low | behavior |
| [FEAT-10 — A `confarg explain` command showing the final configuration and each value's origin](FEAT-10-confarg-explain-command.md) | XL | low | behavior |
| [FEAT-11 — Configuration versioning and a migration registry](FEAT-11-config-versioning-and-migrations.md) | XL | high | config |
| [FEAT-12 — Carefully scoped expression expansion](FEAT-12-scoped-expression-expansion.md) | L | high | behavior |
| [FEAT-13 — Struct types that are generic](FEAT-13-generic-struct-types.md) | L | high | behavior |
| [FEAT-14 — Dataclass fields that are not `__init__` parameters](FEAT-14-dataclass-fields-outside-init.md) | L | high | behavior |
| [FEAT-15 — No way to inspect the flags of a class the tag has not named yet](FEAT-15-inspect-flags-of-unnamed-class.md) | M | low | behavior |
| [FEAT-16 — Let `__cast__` name a leaf type by dotted path](FEAT-16-dotted-cast-names.md) | M | medium | behavior |
| [FEAT-17 — An end-of-options separator (`--`)](FEAT-17-end-of-options-separator.md) | M | medium | behavior |
| [FEAT-18 — The environment channel has no append spelling](FEAT-18-no-append-spelling-in-the-environment.md) | M | low | behavior |
| [FEAT-19 — App-declared defaults, mounted at the type that declares them](FEAT-19-app-declared-defaults.md) | L | medium | behavior |
| [FEAT-20 — Derived values that cannot be made inconsistent](FEAT-20-enforced-derived-values.md) | M | medium | behavior |

<!-- tickets:end -->

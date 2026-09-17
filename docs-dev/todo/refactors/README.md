# Refactors

Code that works but should be cleaner: duplication, misplaced modules, dead weight, test
hygiene, performance. One ticket per file; see [../README.md](../README.md) for the format.

A refactor whose impact is anything but `none` is not really a refactor — it reaches users, and
wants either a decision in
[../../architecture/10-design-decisions.md](../../architecture/10-design-decisions.md) or a
different board.

<!-- tickets:start -->

| Ticket | Effort | Risk | Impact |
|---|---|---|---|
| [REF-2 — The scalar-cast table exists three times](REF-2-scalar-cast-table-duplicated.md) | S | medium | none |
| [REF-3 — `_add_*` wrappers survive only for completion](REF-3-add-wrappers-survive-for-completion.md) | M | medium | none |
| [REF-4 — `tests/examples/_registry.py` is orphaned](REF-4-orphaned-examples-registry.md) | S | low | none |
| [REF-6 — `LIST_APPEND_KEY` accepts a value nothing produces](REF-6-list-append-key-unreachable-value.md) | S | high | none |
| [REF-7 — Expression resolution repeats work](REF-7-expression-resolution-repeats-work.md) | M | medium | none |
| [REF-9 — Review public argument names and order](REF-9-review-public-argument-names.md) | L | medium | api |
| [REF-10 — Sweep for code obsoleted by past refactors](REF-10-sweep-obsoleted-code.md) | M | high | none |
| [REF-14 — A dynamic-flag test passes for the wrong reason](REF-14-dynamic-flag-test-passes-wrongly.md) | S | low | none |
| [REF-15 — `examples/17_removing_items/myapp.py` imports a module that does not exist](REF-15-example-imports-missing-module.md) | S | low | behavior |
| [REF-17 — `_var_param_names` / `_var_positional_name` / `_var_keyword_name` re-inspect the same signature](REF-17-var-param-helpers-reinspect-signature.md) | S | low | none |
| [REF-18 — `_resolve_single` duplicates its exception-handling chain](REF-18-resolve-single-duplicate-exception-chain.md) | S | low | none |
| [REF-19 — YAML/JSON dict loaders duplicate their item-loader counterparts](REF-19-yaml-json-loader-duplication.md) | S | low | none |
| [REF-21 — `_construct_sequence` / `_construct_list` / `_construct_set` are three thin wrappers](REF-21-construct-collection-thin-wrappers.md) | S | low | none |
| [REF-22 — `_store_env_value` buries a JSON-autodetect predicate in nested `any(...)` calls](REF-22-store-env-value-json-predicate.md) | S | low | none |
| [REF-23 — `_build_leaf_spec` repeats `group` / `group_description` on every FlagSpec](REF-23-build-leaf-spec-repeats-group.md) | S | low | none |
| [REF-24 — Minor cleanups in `_parse_cli` and `_coerce`](REF-24-parse-cli-and-coerce-cleanups.md) | S | low | none |
| [REF-26 — The `--config` files named on argv are parsed three times per run](REF-26-config-files-parsed-three-times.md) | M | low | none |
| [REF-27 — Tests of the neutral flag model still live under `tests/cli/argparse/`](REF-27-neutral-flag-tests-under-argparse.md) | M | low | none |
| [REF-28 — Three example scripts fail `ruff` on a clean tree](REF-28-examples-fail-ruff.md) | S | low | none |

<!-- tickets:end -->

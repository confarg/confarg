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
| [REF-4 — `tests/examples/_registry.py` is orphaned](REF-4-orphaned-examples-registry.md) | S | low | none |
| [REF-9 — Review public argument names and order](REF-9-review-public-argument-names.md) | L | medium | api |
| [REF-10 — Sweep for code obsoleted by past refactors](REF-10-sweep-obsoleted-code.md) | M | high | none |
| [REF-15 — `examples/17_removing_items/myapp.py` imports a module that does not exist](REF-15-example-imports-missing-module.md) | S | low | behavior |
| [REF-26 — The `--config` files named on argv are parsed three times per run](REF-26-config-files-parsed-three-times.md) | M | low | none |
| [REF-27 — Tests of the neutral flag model still live under `tests/cli/argparse/`](REF-27-neutral-flag-tests-under-argparse.md) | M | low | none |
| [REF-28 — Three example scripts fail `ruff` on a clean tree](REF-28-examples-fail-ruff.md) | S | low | none |
| [REF-29 — Every file under `examples/` is stored with CRLF](REF-29-examples-stored-with-crlf.md) | S | low | none |
| [REF-33 — `_build_leaf_spec` carries a dead `tuple[X, ...]` fallback branch](REF-33-dead-tuple-varlen-fallback-branch.md) | S | low | none |
| [REF-34 — An _attribute_chain test asserts what it does not verify](REF-34-attribute-chain-test-asserts-nothing.md) | S | low | none |
| [REF-38 — `test_collect_names_keyword_args` or-asserts away its own claim](REF-38-collect-names-keyword-args-or-asserts-away-claim.md) | S | low | none |
| [REF-39 — `test_dict_field_from_env` or-asserts away its own claim](REF-39-dict-field-env-test-or-asserts-away-claim.md) | S | low | none |

<!-- tickets:end -->

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
| [REF-38 — `test_collect_names_keyword_args` or-asserts away its own claim](REF-38-collect-names-keyword-args-or-asserts-away-claim.md) | S | low | none |
| [REF-39 — `test_dict_field_from_env` or-asserts away its own claim](REF-39-dict-field-env-test-or-asserts-away-claim.md) | S | low | none |
| [REF-40 — The nine-keyword option surface is spelled out fourteen times](REF-40-option-surface-spelled-fourteen-times.md) | L | medium | behavior |
| [REF-41 — `cli/click/_context.py` and `cli/typer/_context.py` are the same file](REF-41-click-and-typer-context-are-the-same-file.md) | S | low | none |
| [REF-42 — `argparse/_completion.py` re-implements the `cli/_build.py` type walk](REF-42-argparse-completion-reimplements-the-build-walk.md) | M | medium | none |
| [REF-43 — Four copies of the type-tree path walk in `_parse_cli.py`](REF-43-parse-cli-path-walk-copies.md) | M | high | none |
| [REF-44 — The CLI root `--json` fold duplicates `_parse_env._fold_root_json`](REF-44-cli-root-json-fold-duplicates-the-env-one.md) | S | low | none |
| [REF-45 — The argv value-run scan and its missing-value guard are written seven and five times](REF-45-argv-value-run-scan-duplicated.md) | M | high | none |
| [REF-46 — Near-duplicate helper pairs in the merge core](REF-46-near-duplicate-helpers-in-the-merge-core.md) | S | low | none |
| [REF-47 — The shape-dispatch chain is repeated five times](REF-47-shape-dispatch-chain-repeated-five-times.md) | L | high | none |
| [REF-48 — `inspect.signature` is walked four or five times per struct](REF-48-init-signature-walked-five-times.md) | M | high | none |
| [REF-49 — `graphlib.TopologicalSorter` replaces the hand-written Kahn loop](REF-49-graphlib-replaces-hand-written-kahn.md) | S | low | behavior |
| [REF-50 — Adapter registration and completion boilerplate](REF-50-adapter-registration-boilerplate.md) | M | low | none |
| [REF-51 — Hot error messages and the dotted-name format live outside their owners](REF-51-error-messages-outside-the-factories.md) | M | low | none |
| [REF-52 — Mechanical collapses in the type machinery](REF-52-mechanical-collapses-in-the-type-machinery.md) | S | low | none |
| [REF-53 — Nine `try`/`except`/`pass` blocks that `contextlib.suppress` already spells](REF-53-contextlib-suppress-for-hand-rolled-try-except.md) | S | low | none |
| [REF-54 — Three hand-written scan loops in `dictexpr` the stdlib writes in one line](REF-54-dictexpr-scan-loops-are-re-sub-and-accumulate.md) | S | low | none |
| [REF-55 — Two adjacent-pair loops written with indices instead of `itertools.pairwise`](REF-55-pairwise-for-index-window-loops.md) | S | low | none |
| [REF-56 — Seven `[len(prefix):]` slices that are `str.removeprefix`](REF-56-removeprefix-for-guarded-slices.md) | S | low | none |
| [REF-57 — Small stdlib swaps across the core](REF-57-small-stdlib-swaps-in-the-core.md) | S | low | none |

<!-- tickets:end -->

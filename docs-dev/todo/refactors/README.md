# Refactors

Code that works but should be cleaner: duplication, misplaced modules, dead weight, test
hygiene, performance. One ticket per file; see [../README.md](../README.md) for the format.

A refactor whose impact is anything but `none` is not really a refactor — it reaches users, and
wants either a decision in
[../../architecture/design-decisions/README.md](../../architecture/design-decisions/README.md) or a
different board.

<!-- tickets:start -->

| Ticket | Effort | Risk | Impact |
|---|---|---|---|
| [REF-9 — Review public argument names and order](REF-9-review-public-argument-names.md) | L | medium | api |
| [REF-10 — Sweep for code obsoleted by past refactors](REF-10-sweep-obsoleted-code.md) | M | high | none |
| [REF-26 — The `--config` files named on argv are parsed three times per run](REF-26-config-files-parsed-three-times.md) | M | low | none |
| [REF-27 — Tests of the neutral flag model still live under `tests/cli/argparse/`](REF-27-neutral-flag-tests-under-argparse.md) | M | low | none |
| [REF-41 — `cli/click/_context.py` and `cli/typer/_context.py` are the same file](REF-41-click-and-typer-context-are-the-same-file.md) | S | low | none |
| [REF-42 — `argparse/_completion.py` re-implements the `cli/_build.py` type walk](REF-42-argparse-completion-reimplements-the-build-walk.md) | M | medium | none |
| [REF-43 — Four copies of the type-tree path walk in `_parse_cli.py`](REF-43-parse-cli-path-walk-copies.md) | M | high | none |
| [REF-45 — The argv value-run scan is written seven times](REF-45-argv-value-run-scan-duplicated.md) | M | high | none |
| [REF-46 — Near-duplicate helper pairs in the merge core](REF-46-near-duplicate-helpers-in-the-merge-core.md) | S | low | none |
| [REF-48 — `inspect.signature` is walked four or five times per struct](REF-48-init-signature-walked-five-times.md) | M | high | none |
| [REF-49 — `graphlib.TopologicalSorter` replaces the hand-written Kahn loop](REF-49-graphlib-replaces-hand-written-kahn.md) | S | low | behavior |
| [REF-50 — Adapter registration and completion boilerplate](REF-50-adapter-registration-boilerplate.md) | M | low | none |
| [REF-52 — Mechanical collapses in the type machinery](REF-52-mechanical-collapses-in-the-type-machinery.md) | S | low | none |
| [REF-53 — Four `try`/`except`/`pass` blocks that `contextlib.suppress` already spells](REF-53-contextlib-suppress-for-hand-rolled-try-except.md) | S | low | none |
| [REF-54 — Three hand-written scan loops in `dictexpr` the stdlib writes in one line](REF-54-dictexpr-scan-loops-are-re-sub-and-accumulate.md) | S | low | none |
| [REF-55 — An adjacent-pair loop written with indices instead of `itertools.pairwise`](REF-55-pairwise-for-index-window-loops.md) | S | low | none |
| [REF-56 — Four `[len(prefix):]` slices that are `str.removeprefix`](REF-56-removeprefix-for-guarded-slices.md) | S | low | none |
| [REF-57 — Small stdlib swaps across the core](REF-57-small-stdlib-swaps-in-the-core.md) | S | low | none |
| [REF-58 — The config-parallel struct walk has two owners](REF-58-config-parallel-struct-walk-has-two-owners.md) | S | medium | none |
| [REF-59 — Twenty code blocks under `examples/` are still hand-copied](REF-59-example-code-blocks-not-generated.md) | M | low | none |
| [REF-60 — Nothing asserts the bytes `dump_file` writes](REF-60-dumped-file-bytes-are-never-asserted.md) | S | medium | none |
| [REF-62 — Hidden backend blocks are replayed twice per section in the example READMEs](REF-62-duplicated-hidden-backend-blocks-in-examples.md) | S | low | none |
| [REF-63 — `13_collection_items` carries an empty section and a misplaced tuple remark](REF-63-collection-items-readme-empty-section-and-misplaced-remark.md) | S | low | none |
| [REF-64 — The clicklike completion tests assert that nothing was added](REF-64-completion-tests-assert-nothing-was-added.md) | S | medium | none |
| [REF-66 — the pinned ruff and the project's own ruff disagree](REF-66-pinned-ruff-disagrees-with-the-project-ruff.md) | S | low | none |
| [REF-68 — the scalar root spec undoes the multi-token shape one attribute at a time](REF-68-scalar-root-undoes-the-multi-token-shape-one-field-at-a-time.md) | S | low | none |
| [REF-69 — Two construction-error sentences are still spelled at every call site in `typedload/`](REF-69-typedload-construction-messages-still-at-their-call-sites.md) | S | low | none |
| [REF-70 — `_dataclass_subclasses` is named for dataclasses but returns plain-class structs](REF-70-dataclass-subclasses-is-a-misnomer.md) | M | low | none |
| [REF-71 — Three functions answer "does this segment name a member?", and they disagree at the edges](REF-71-three-answers-to-is-this-a-member.md) | M | medium | none |
| [REF-75 — `cli/_collect.py` no longer collects, and `_merge_from_flat` no longer merges from the flat result](REF-75-cli-collect-module-no-longer-collects.md) | S | low | none |
| [REF-76 — `FlagSpec.accumulates` has no reader left in the merge](REF-76-flagspec-accumulates-has-no-reader-left.md) | S | low | none |

<!-- tickets:end -->

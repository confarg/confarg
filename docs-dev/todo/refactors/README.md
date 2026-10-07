# Refactors

Code that works but should be cleaner: duplication, misplaced modules, dead weight, test
hygiene, performance. One ticket per file; see [../README.md](../README.md) for the format.

A refactor whose impact is anything but `none` is not really a refactor — it reaches users, and
wants either a decision in
[../../architecture/design-decisions/README.md](../../architecture/design-decisions/README.md) or a
different board.

<!-- tickets:start -->

| Ticket | Severity | Blocked by | Effort | Risk | Impact |
|---|---|---|---|---|---|
| [REF-26 — The `--config` files named on argv are parsed three times per run](REF-26-config-files-parsed-three-times.md) | minor |  | M | low | none |
| [REF-41 — `cli/click/_context.py` and `cli/typer/_context.py` are the same file](REF-41-click-and-typer-context-are-the-same-file.md) | trivial |  | S | low | none |
| [REF-46 — Near-duplicate helper pairs in the merge core](REF-46-near-duplicate-helpers-in-the-merge-core.md) | trivial |  | S | low | none |
| [REF-49 — `graphlib.TopologicalSorter` replaces the hand-written Kahn loop](REF-49-graphlib-replaces-hand-written-kahn.md) | trivial |  | S | low | behavior |
| [REF-54 — Two span loops in `dictexpr` that one helper writes](REF-54-dictexpr-span-loops-share-one-helper.md) | trivial |  | S | low | none |
| [REF-55 — An adjacent-pair loop written with indices instead of `itertools.pairwise`](REF-55-pairwise-for-index-window-loops.md) | trivial |  | S | low | none |
| [REF-58 — The config-parallel struct walk has two owners](REF-58-config-parallel-struct-walk-has-two-owners.md) | trivial |  | S | medium | none |
| [REF-59 — Two `type` blocks under `examples/` wait on the hook; the rest is generated](REF-59-example-code-blocks-not-generated.md) | trivial |  | S | low | none |
| [REF-60 — Nothing asserts the bytes `dump_file` writes](REF-60-dumped-file-bytes-are-never-asserted.md) | trivial |  | S | medium | none |
| [REF-63 — `13_collection_items` carries an empty section and a misplaced tuple remark](REF-63-collection-items-readme-empty-section-and-misplaced-remark.md) | trivial |  | S | low | none |
| [REF-64 — The clicklike completion tests assert that nothing was added](REF-64-completion-tests-assert-nothing-was-added.md) | trivial |  | S | medium | none |
| [REF-66 — the pinned ruff and the project's own ruff disagree](REF-66-pinned-ruff-disagrees-with-the-project-ruff.md) | trivial |  | S | low | none |
| [REF-68 — the scalar root spec undoes the multi-token shape one attribute at a time](REF-68-scalar-root-undoes-the-multi-token-shape-one-field-at-a-time.md) | trivial |  | S | low | none |
| [REF-75 — `cli/_collect.py` no longer collects, and `_merge_from_flat` no longer merges from the flat result](REF-75-cli-collect-module-no-longer-collects.md) | trivial |  | S | low | none |
| [REF-77 — The four "expected N elements" refusals have drifted on the type's name](REF-77-expected-elements-refusals-have-drifted.md) | trivial |  | S | medium | none |
| [REF-78 — `.ruff.toml` selects "PL" twice](REF-78-ruff-toml-selects-pl-twice.md) | trivial |  | S | low | none |
| [REF-81 — `90_integration/README.md` opens at h3 and sandwiches a lone h2 between h3 sections](REF-81-integration-readme-heading-structure.md) | trivial |  | S | low | none |
| [REF-82 — `greetings.py` in two examples carries a dead `Config` dataclass](REF-82-greetings-py-carries-a-dead-config-dataclass.md) | trivial |  | S | low | none |
| [REF-84 — The delete suffix and its list index are decoded twice](REF-84-env-delete-suffix-decoded-twice.md) | trivial |  | S | low | none |
| [REF-85 — `api-seams.md`'s round-trip paragraphs sit under the option-set heading](REF-85-api-seams-round-trip-paragraphs-sit-under-the-option-set-heading.md) | trivial |  | S | low | none |
| [REF-86 — The collection-patch question stops at a callable for nothing](REF-86-the-collection-patch-question-stops-at-a-callable-for-nothing.md) | trivial |  | S | low | none |
| [REF-87 — An append is combined with what its path holds in two functions](REF-87-an-append-is-combined-with-the-path-in-two-functions.md) | trivial |  | S | medium | none |
| [REF-10 — Sweep for code obsoleted by past refactors](REF-10-sweep-obsoleted-code.md) | trivial |  | M | high | none |
| [REF-27 — Tests of the neutral flag model still live under `tests/cli/argparse/`](REF-27-neutral-flag-tests-under-argparse.md) | trivial |  | M | low | none |
| [REF-42 — `argparse/_completion.py` re-implements the `cli/_build.py` type walk](REF-42-argparse-completion-reimplements-the-build-walk.md) | trivial |  | M | medium | none |
| [REF-45 — The argv value-run scan is written seven times](REF-45-argv-value-run-scan-duplicated.md) | trivial |  | M | high | none |
| [REF-50 — Adapter registration and completion boilerplate](REF-50-adapter-registration-boilerplate.md) | trivial |  | M | low | none |
| [REF-70 — `_dataclass_subclasses` is named for dataclasses but returns plain-class structs](REF-70-dataclass-subclasses-is-a-misnomer.md) | trivial |  | M | low | none |
| [REF-71 — Four functions answer "does this segment name a member?", and they disagree at the edges](REF-71-three-answers-to-is-this-a-member.md) | trivial |  | M | medium | none |
| [REF-83 — The registration walk dispatches on shape outside `_type_kind`](REF-83-registration-walk-dispatches-outside-the-kind-table.md) | trivial |  | M | medium | none |

<!-- tickets:end -->

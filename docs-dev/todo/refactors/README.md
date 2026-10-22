# Refactors

Code that works but should be cleaner: duplication, misplaced modules, dead weight, test hygiene, performance.
One ticket per file; see [../README.md](../README.md) for the format.

A refactor whose impact is anything but `none` is not really a refactor — it reaches users, and wants either a decision in [../../architecture/design-decisions/README.md](../../architecture/design-decisions/README.md) or a different board.

Working on refactoring should never modify tests, unless the ticket is about refactoring tests.

<!-- tickets:start -->

| Ticket | Severity | Blocked by | Effort | Risk | Impact |
|---|---|---|---|---|---|
| [REF-26 — The `--config` files named on argv are parsed three times per run](REF-26-config-files-parsed-three-times.md) | minor |  | M | low | none |
| [REF-41 — `cli/click/_context.py` and `cli/typer/_context.py` are the same file](REF-41-click-and-typer-context-are-the-same-file.md) | trivial |  | S | low | none |
| [REF-46 — Near-duplicate helper pairs in the merge core](REF-46-near-duplicate-helpers-in-the-merge-core.md) | trivial |  | S | low | none |
| [REF-55 — An adjacent-pair loop written with indices instead of `itertools.pairwise`](REF-55-pairwise-for-index-window-loops.md) | trivial |  | S | low | none |
| [REF-58 — The config-parallel struct walk has two owners](REF-58-config-parallel-struct-walk-has-two-owners.md) | trivial |  | S | medium | none |
| [REF-59 — Two `type` blocks under `examples/` wait on the hook; the rest is generated](REF-59-example-code-blocks-not-generated.md) | trivial |  | S | low | none |
| [REF-63 — `13_collection_items` carries an empty section and a misplaced tuple remark](REF-63-collection-items-readme-empty-section-and-misplaced-remark.md) | trivial |  | S | low | none |
| [REF-64 — The clicklike completion tests assert that nothing was added](REF-64-completion-tests-assert-nothing-was-added.md) | trivial |  | S | medium | none |
| [REF-75 — `cli/_collect.py` no longer collects, and `_merge_from_flat` no longer merges from the flat result](REF-75-cli-collect-module-no-longer-collects.md) | trivial |  | S | low | none |
| [REF-77 — The four "expected N elements" refusals have drifted on the type's name](REF-77-expected-elements-refusals-have-drifted.md) | trivial |  | S | medium | none |
| [REF-82 — `greetings.py` in two examples carries a dead `Config` dataclass](REF-82-greetings-py-carries-a-dead-config-dataclass.md) | trivial |  | S | low | none |
| [REF-85 — `api-seams.md`'s round-trip paragraphs sit under the option-set heading](REF-85-api-seams-round-trip-paragraphs-sit-under-the-option-set-heading.md) | trivial |  | S | low | none |
| [REF-94 — Construction reads a sequence's index keys in two places](REF-94-construction-reads-a-sequences-index-keys-in-two-places.md) | trivial |  | S | medium | none |
| [REF-95 — The tag-collision tests leave their warnings uncaptured](REF-95-the-tag-collision-tests-leave-their-warnings-uncaptured.md) | trivial |  | S | low | none |
| [REF-97 — How a message names a type is spelled by hand in a dozen places](REF-97-how-a-message-names-a-type-is-spelled-by-hand.md) | trivial |  | S | low | none |
| [REF-98 — `_typed_read._read` and `_serialize.written_form` are one walk spelled twice](REF-98-typed_read-read-and-written-form-are-one-walk.md) | trivial |  | S | low | none |
| [REF-99 — `read_union_leaf` reads a union's variants under the default `union_tag`](REF-99-read_union_leaf-spells-the-default-union-tag.md) | trivial |  | S | low | none |
| [REF-101 — `_coerce_type_ref` repeats the class-tag import step for step](REF-101-coerce-type-ref-repeats-the-class-tag-import.md) | trivial |  | S | low | none |
| [REF-102 — `make_parser` tells a merge option from a parser keyword by its own test](REF-102-make-parser-tells-a-merge-option-by-its-own-test.md) | trivial |  | S | low | none |
| [REF-103 — `_pending_prefixes` walks the data by its own steps rather than `_step`](REF-103-pending-prefixes-walks-the-data-without-step.md) | trivial |  | S | medium | none |
| [REF-104 — The locals layer reading combines a list item and its patch shallowly](REF-104-the-locals-layer-reading-combines-an-item-and-its-patch-shallowly.md) | trivial |  | S | medium | none |
| [REF-109 — A message names the root position by hand eleven times](REF-109-a-message-names-the-root-position-by-hand.md) | trivial |  | S | low | none |
| [REF-113 — A format's `holds` predicate restates its native types](REF-113-a-formats-holds-predicate-restates-its-native-types.md) | trivial |  | S | low | none |
| [REF-114 — Each adapter reconciles its registration by hand](REF-114-each-adapter-reconciles-its-registration-by-hand.md) | trivial |  | S | low | none |
| [REF-115 — `_format_offset` slices an `isoformat()` string where `strftime("%:z")` says it](REF-115-format-offset-slices-an-isoformat-string.md) | trivial |  | S | low | none |
| [REF-116 — The dump opens and closes an instance by hand, twice](REF-116-the-dump-opens-and-closes-an-instance-by-hand-twice.md) | trivial |  | S | low | none |
| [REF-117 — Two depth bounds share a name, and two rules elide a long path](REF-117-two-depth-bounds-share-a-name-and-two-rules-elide-a-path.md) | trivial |  | S | low | none |
| [REF-10 — Sweep for code obsoleted by past refactors](REF-10-sweep-obsoleted-code.md) | trivial |  | M | high | none |
| [REF-27 — Tests of the neutral flag model still live under `tests/cli/argparse/`](REF-27-neutral-flag-tests-under-argparse.md) | trivial |  | M | low | none |
| [REF-42 — `argparse/_completion.py` re-implements the `cli/_build.py` type walk](REF-42-argparse-completion-reimplements-the-build-walk.md) | trivial |  | M | medium | none |
| [REF-45 — The argv value-run scan is written seven times](REF-45-argv-value-run-scan-duplicated.md) | trivial |  | M | high | none |
| [REF-50 — Adapter registration and completion boilerplate](REF-50-adapter-registration-boilerplate.md) | trivial |  | M | low | none |
| [REF-71 — Four functions answer "does this segment name a member?", and they disagree at the edges](REF-71-three-answers-to-is-this-a-member.md) | trivial |  | M | medium | none |
| [REF-83 — The registration walk dispatches on shape outside `_type_kind`](REF-83-registration-walk-dispatches-outside-the-kind-table.md) | trivial |  | M | medium | none |
| [REF-91 — The documentation written before the no-hard-wrap rule is still hard-wrapped](REF-91-the-older-documentation-is-hard-wrapped.md) | trivial |  | M | low | none |
| [REF-105 — A fixed-length position is read and spelled by hand around `_fixed_position`](REF-105-a-fixed-length-position-is-read-and-spelled-per-site.md) | trivial |  | M | low | none |
| [REF-108 — The library steers by process-wide warning filters](REF-108-the-library-steers-by-process-wide-warning-filters.md) | trivial |  | M | medium | none |
| [REF-111 — `_merge`, `_types` and `dictexpr` import each other, through two small leaves](REF-111-merge-types-and-dictexpr-import-each-other.md) | trivial |  | M | low | none |

<!-- tickets:end -->

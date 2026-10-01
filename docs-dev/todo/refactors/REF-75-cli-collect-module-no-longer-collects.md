# REF-75 — `cli/_collect.py` no longer collects, and `_merge_from_flat` no longer merges from the flat result

**Where:** `src/confarg/cli/_collect.py` and its importers (`cli/argparse/_namespace.py`,
`cli/_clicklike/_context.py`, `cli/cyclopts/_context.py`, `cli/argparse/_completion.py`) ·
**Filed:** 2026-10-01
**Effort:** S · **Risk:** low · **Impact:** none

Since REF-72 the module holds the adapters' merge tail — the argv check, the call to vanilla's
loop, `_merge_sources` — plus `_tag_named_struct`, which only argparse completion uses. The
type walk it was named for is gone, and `_merge_from_flat` takes the flat parse result only to
check it against argv. The names now describe the superseded design, and the notes and the
canonical table cite `cli/_collect` for things that are not collection. Fix direction: rename
the module (`cli/_merge_tail.py`, say) and the function (`_merge_from_argv`), move
`_tag_named_struct` next to its one caller, and sweep the `cli/_collect` citations in
`../../architecture/` (run `uv run python docs-dev/todo/anchors.py` after). See
[cli-adapters/model.md#argv-is-the-only-writer](../../architecture/cli-adapters/model.md#argv-is-the-only-writer).

# REF-67 — a console block is duplicated in the collections tutorial

**Where:** `examples/12_collections/README.md` · **Filed:** 2026-09-28
**Effort:** S · **Risk:** low · **Impact:** none

The hidden `list_of_ints_cyclopts.py --input` block appears twice in a row, so the same command
runs twice as a subprocess test on every full `uv run pytest`
([12-testing.md#examples-and-documentation](../../architecture/12-testing.md#examples-and-documentation)).
Its neighbours cover argparse and cyclopts once each; the second copy looks like a click or typer
block that was pasted and never retargeted — and those two are genuinely absent here because a bare
`--input` is what they reject (BUG-38). Delete the duplicate.

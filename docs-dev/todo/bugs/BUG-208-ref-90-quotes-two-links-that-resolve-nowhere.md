---
filed: 2026-10-08
where:
  - docs-dev/todo/refactors/REF-90-two-notes-cite-a-note-as-04-its-pre-split-number.md
effort: S
risk: low
impact: none
severity: trivial
introduced_by: unknown  # born in the REF-90 filing revision itself (jj change nxnvxwkyyqsw, local, not yet a PR), which pasted the two citations verbatim from the notes; no other revision has touched the file
---
# BUG-208 — REF-90's own file carries the two citations it quotes as live links, and neither resolves from the board folder

The ticket quotes the two stale `[04]` citations as Markdown links. Their targets resolve from the notes they sit in — `docs-dev/architecture/cli-parsing/token-consumption.md` and `docs-dev/architecture/environment-parsing.md` — but not from `docs-dev/todo/refactors/`, so the anchors sweep exits non-zero over the very ticket that exists to fix stale citations. The sweep follows links but not code spans, so quoting the citations verbatim as code spans keeps the quotes exact and the sweep green.

Origin: born broken in the filing of REF-90 itself — the citations were pasted verbatim from the two notes, and their relative targets do not survive the change of folder. Neither a regression nor latent: nothing worked before the ticket existed.

```console
$ uv run python docs-dev/todo/anchors.py
error: docs-dev/todo/refactors/REF-90-two-notes-cite-a-note-as-04-its-pre-split-number.md:15: links ../cli-adapters/whole-value-flags.md#whole-value-flags, but there is no such file
error: docs-dev/todo/refactors/REF-90-two-notes-cite-a-note-as-04-its-pre-split-number.md:16: links cli-adapters/whole-value-flags.md#whole-value-flags, but there is no such file
# expected: the quoted citations sit in code spans the sweep does not follow, and it reports no error for this file
# actual:   both quotes are live links into folders that do not exist beside the board
```

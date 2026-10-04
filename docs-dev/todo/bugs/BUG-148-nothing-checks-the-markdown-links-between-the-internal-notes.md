---
filed: 2026-10-04
where:
  - docs-dev/todo/anchors.py
  - docs-dev/plans/untyped-config-rewriter.md
effort: M
risk: low
impact: none
---
# BUG-148 — Nothing checks the Markdown links between the internal notes

`docs-dev/todo/anchors.py` checks the citations in `src/` and `tests/` (BUG-105), but the
relative links *inside* `docs-dev/` and `docs-agents/`, about 470 of them
(`[…](../../architecture/invariants.md#cross-channel-parity)`), and the path mentions in prose
are checked by nothing. The renumbering of the architecture notes
([architecture/README.md § Layout](../../architecture/README.md#layout)) has already left them
stale twice: the protocols' links (BUG-141), and three citations of
`01-pipeline-and-contracts.md` by line number in `docs-dev/plans/untyped-config-rewriter.md`
(lines 73, 160, 222). That note is now the `pipeline/` folder, and line numbers would not survive
an edit even if it still existed. Fix direction: resolve every relative Markdown link (and
repo-root path in backticks) under `docs-dev/` and `docs-agents/` to a file, and its anchor to a
heading, reusing `anchors.py`'s `_anchors`. Repoint the plan's three citations to
`pipeline/<subtopic>.md#<anchor>`. Once the sweep exists, FEAT-25 puts it in CI with the rest.

```console
$ grep -n "01-pipeline-and-contracts" docs-dev/plans/untyped-config-rewriter.md
73:`01-pipeline-and-contracts.md:106`). This tool needs the opposite: the document must exist before
160:the seam `01-pipeline-and-contracts.md:46` describes).
222:     does not guarantee this (`01-pipeline-and-contracts.md:59`); for a rewriter it is the point.
$ ls docs-dev/architecture/01-pipeline-and-contracts.md
ls: cannot access 'docs-dev/architecture/01-pipeline-and-contracts.md': No such file or directory
$ uv run python docs-dev/todo/anchors.py
61 document(s) cited, every anchor resolves
# expected: the three stale citations reported
# actual:   exit 0 — Markdown under docs-dev/ is outside the sweep
```

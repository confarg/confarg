# BUG-49 — A `Dev Notes:` citation points at `#the-triad`, a heading renamed to `## The quartet`

**Where:** `src/confarg/cli/_collect.py:686` · **Filed:** 2026-09-26
**Effort:** S · **Risk:** low · **Impact:** none

`_collect.py:686` cites
[04-cli-adapters.md#the-triad](../../architecture/04-cli-adapters.md), but that document's
heading is `## The quartet` — renamed when typer joined argparse, click and cyclopts as a fourth
adapter. The citation resolves to the document and then to nothing, so a reader following it
lands at the top of the note and has to guess which section was meant.

`docs-agents/docstrings.md` makes this the rule the rename missed: "Renaming a cited heading means
fixing every citation that names it (`grep -rn "<old-anchor>" src/`)". This is the only surviving
instance — the other five citations flagged by an anchor sweep were false positives, anchors
containing an underscore (`#cli_prefix`, `#union_tag-defaults-to-class`), which do resolve.

The fix is one word, but the sweep is worth doing with it: a check that every
`docs-dev/architecture/*.md#anchor` in `src/` names a heading that exists would belong beside
`docs-dev/todo/index.py`, which already validates what it reads.

**Reproduction**

<!-- pytest-markdown-console-file: notest -->
```console
$ grep -n 'the-triad' src/confarg/cli/_collect.py
686:        docs-dev/architecture/04-cli-adapters.md#the-triad

$ grep -c '^## The triad' docs-dev/architecture/04-cli-adapters.md
0

$ grep -n '^## The quartet' docs-dev/architecture/04-cli-adapters.md
11:## The quartet
```

Expected: the cited anchor names a heading in the cited document. Actual: no heading generates
`#the-triad`; the section it refers to is `#the-quartet`.

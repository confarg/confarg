# BUG-141 — The protocols link the architecture notes by their old numbered filenames

**Where:** `docs-agents/boards.md`, `docs-agents/bug-fixing.md`, `docs-agents/docstrings.md`,
`docs-agents/feature-design.md`, `docs-agents/working-with-architecture.md` ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** medium · **Impact:** none

The architecture notes were unnumbered (`invariants.md`, `design-decisions/`, `cli-adapters/`,
`types/`, `expressions/` — see [architecture/README.md § Layout](../../architecture/README.md#layout)),
but 12 references across the five protocol files still spell the old numbered names — 9 of them
`09-invariants.md` and `10-design-decisions.md`, which every protocol names as a step. A link that
names a file that does not exist sends an agent reading cold back to `architecture/README.md` to
rediscover the map. The anchors check does not catch this: `docs-dev/todo/anchors.py` inspects the
citations in `docs-dev/` and reports "51 document(s) cited, every anchor resolves", and the
protocols are `.gitignore`d, outside its scan. Found while fixing REF-57 (the small-stdlib-swaps ticket, closed 2026-10-03);
`docs-agents/` is untracked, so the references are identical on every revision — nothing in the
fix for REF-57 touched them.

Fix direction: point each reference at the file or folder that holds the content now
(`invariants.md`, `design-decisions/`, `cli-adapters/`, `types/`, `expressions/`), and consider
having `anchors.py` (or [BUG-105](BUG-105-the-anchor-sweep-cannot-see-citations-under-tests-or-short-form-spellings.md))
cover the protocols' links into `docs-dev/` so the drift cannot come back. Editing a protocol file
means running `uv run python docs-agents/archive.py` afterwards.

```console
$ grep -rn "09-invariants\.md\|10-design-decisions\.md" docs-agents/*.md | wc -l
9
$ ls docs-dev/architecture/09-invariants.md docs-dev/architecture/10-design-decisions.md
ls: cannot access 'docs-dev/architecture/09-invariants.md': No such file or directory
ls: cannot access 'docs-dev/architecture/10-design-decisions.md': No such file or directory
```

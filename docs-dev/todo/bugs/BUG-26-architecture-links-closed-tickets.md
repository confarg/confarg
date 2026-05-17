# BUG-26 — Architecture notes link closed tickets to a board that cannot hold them

**Where:** `docs-dev/architecture/` (16 links) · **Filed:** 2026-09-16
**Effort:** S · **Risk:** low · **Impact:** none

Sixteen links name a ticket that has already closed and point at the board index — which, by
the boards-hold-open-work-only rule, never mentions that ticket and never will. The link
resolves and answers nothing: a reader who follows it learns only that the board exists. Four
sibling links, to tickets still open, do reach the entry they name, so the two kinds are
indistinguishable until clicked. Splitting the boards into one file per ticket made this
visible rather than causing it — before the split the same links landed on a board file whose
entry had already been deleted.

Three ways out, none obviously right. **Unlink a closed ID**, leaving plain text: honest, and
loses the reader's only lead. **Point at the revision that closed it** — `jj` can find it from
the ID in the description — which is precise, but no link syntax for a revision exists in these
notes yet. Or **let the decision carry the reference**: closing a ticket is already supposed to
record its decision in these very notes, so the ID is redundant and the surrounding sentence
should name the decision instead. The third is the only one that leaves no dangling reference
at all, and it is the most work.

<!-- pytest-markdown-console-file: notest -->

```console
$ grep -c '](../todo/[a-z]*/README.md), closed' docs-dev/architecture/*.md | grep -v ':0$'
docs-dev/architecture/04-cli-adapters.md:3
docs-dev/architecture/05-types-and-construction.md:1
docs-dev/architecture/10-design-decisions.md:12

$ sed -n '153p' docs-dev/architecture/04-cli-adapters.md
`--<field>.class` opener does ([BUG-22](../todo/bugs/README.md), closed). Neither half of that is a
# expected: a target that names BUG-22
# actual:   docs-dev/todo/bugs/README.md — an index of open tickets, none of them BUG-22
```

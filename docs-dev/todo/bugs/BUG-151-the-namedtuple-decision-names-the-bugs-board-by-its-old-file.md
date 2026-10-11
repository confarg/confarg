---
filed: 2026-10-04
where:
  - docs-dev/architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md
effort: S
risk: low
impact: none
severity: trivial
introduced_by: [PR-162]  # docs(todo): Split the boards into one file per ticket
---
# BUG-151 — The namedtuple decision names the bugs board by its old file

[namedtuple-is-a-fixed-length-sequence.md](../../architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md)
closes on "the next free number on `bugs.md` is what the rule intends", but the board has been
the `bugs/` folder, one file per ticket, since the boards were split
([todo/README.md#one-ticket-one-file](../README.md#one-ticket-one-file)). A reader looking for
`bugs.md` finds nothing. Fix direction: say `bugs/`.

Origin: regression from PR-162, which split `bugs.md` into one file per ticket and did not update
this sentence, written by BUG-16's fix the day before, while `bugs.md` was still the board.

```console
$ grep -n "bugs\.md" docs-dev/architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md
67:next free number on `bugs.md` is what the rule intends.
$ ls docs-dev/todo/bugs.md
ls: cannot access 'docs-dev/todo/bugs.md': No such file or directory
# expected: the note names the board as it is now, docs-dev/todo/bugs/
# actual:   it names a file that no longer exists
```

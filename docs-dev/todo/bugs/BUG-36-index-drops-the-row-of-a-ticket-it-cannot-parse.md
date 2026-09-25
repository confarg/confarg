# BUG-36 — `index.py` rewrites a board table without the ticket it just failed to parse

**Where:** `docs-dev/todo/index.py` (`_parse`, `_collect`, `main`) · **Filed:** 2026-09-20
**Effort:** S · **Risk:** low · **Impact:** none

`_parse` returns `None` for a malformed ticket and `_collect` drops it, but `main` writes the
table anyway and only afterwards prints the errors and returns 1. An open ticket whose heading
stops matching therefore loses its row while its file stays on the board — the exact drift the
script exists to prevent, now produced by the generator itself. The one stderr line reads as
"fix this file", not "your board just lost a row", and a caller that ignores the exit code sees
nothing at all. Fix: when `errors` is non-empty, write nothing and return 1 — validation gates
the rewrite instead of running beside it. `--check` already writes nothing, so only the
rewriting branch changes.

<!-- pytest-markdown-console: notest -->
```console
$ grep -c REF-28 docs-dev/todo/refactors/README.md
1
$ sed -i '1s/—/-/' docs-dev/todo/refactors/REF-28-examples-fail-ruff.md   # mangle the heading

$ uv run python docs-dev/todo/index.py
error: refactors/REF-28-examples-fail-ruff.md: first line must read '# <ID> — <headline>'
bugs/: 1 ticket(s), table up to date
features/: 17 ticket(s), table up to date
refactors/: 9 ticket(s), table rewritten
questions/: 0 ticket(s), table up to date
$ echo $?
1

$ ls docs-dev/todo/refactors/REF-28-examples-fail-ruff.md
docs-dev/todo/refactors/REF-28-examples-fail-ruff.md
$ grep -c REF-28 docs-dev/todo/refactors/README.md
0
```

expected: the table is left untouched (`refactors/: table NOT rewritten`), so a board never
loses a row for a ticket that is still open.
actual: `refactors/` drops from 10 rows to 9 while the ticket file is still there.

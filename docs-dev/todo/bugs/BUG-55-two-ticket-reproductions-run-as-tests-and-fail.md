# BUG-55 — Two ticket reproductions run as tests and fail on every full suite

**Where:** `docs-dev/todo/bugs/BUG-49-…md`, `docs-dev/todo/bugs/BUG-52-…md` · **Filed:** 2026-09-29
**Effort:** S · **Risk:** low · **Impact:** none

A documentation defect's reproduction is a `console` block, and `pytest-markdown-console` replays
every one it collects with the Markdown file's *own* directory as the working directory
([12-testing.md#examples-and-documentation](../../architecture/12-testing.md#examples-and-documentation)).
Both of these repros are repo-root-relative (`grep -n … src/confarg/…`, `ls tests/examples/`), so
from `docs-dev/todo/bugs/` they match nothing and fail — permanently, since the block is *meant* to
be read, not run. BUG-46, BUG-47 and BUG-48 face the same thing and carry
`<!-- pytest-markdown-console: notest -->` above the block; these two are missing it.

Two red tests on every full `uv run pytest` is the cost, and it is the expensive kind: it trains a
contributor to read a red summary as normal, so the next real failure hides in it. Adding the
marker to both blocks fixes it. Worth checking whether the marker belongs in the ticket *format*
instead — every documentation-defect repro on these boards needs it, so
[README.md § Reproduction](../README.md#reproduction) could say so rather than leaving each filer to
notice.

<!-- pytest-markdown-console: notest -->
```console
$ uv run pytest docs-dev/todo/bugs/BUG-49-stale-the-triad-citation.md docs-dev/todo/bugs/BUG-52-examples-registry-imports-a-missing-harness.md -q
FF                                                                       [100%]
FAILED docs-dev/todo/bugs/BUG-49-stale-the-triad-citation.md::console[0]@line23
FAILED docs-dev/todo/bugs/BUG-52-examples-registry-imports-a-missing-harness.md::console[0]@line19
2 failed in 3.83s
```

expected: both files collect nothing, as BUG-46 through BUG-48 do — their blocks are documentation,
not commands to run.
actual: two blocks are collected and both fail, because `grep`/`ls` run from
`docs-dev/todo/bugs/` and find neither `src/confarg/` nor `tests/examples/`.

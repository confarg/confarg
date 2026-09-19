# REF-35 — Ticket file committed with CRLF line endings

**Where:** `docs-dev/todo/refactors/REF-34-attribute-chain-test-asserts-nothing.md` · **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

The file landed in revision `mltyuztr` (REF-30) with CRLF terminators on all
14 lines, contrary to the repo's LF convention enforced by the
`mixed-line-ending` pre-commit hook (`--fix=lf` in `.pre-commit-config.yaml`).
`pre-commit run --all-files` rewrites it to LF on the next run, so it was not
run after the file was added. Normalize the file to LF (run
`uv run pre-commit run --all-files` and let the hook fix it). Self-healing, but
it leaves a spurious diff on the board for anyone who runs pre-commit next.

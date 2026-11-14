# The board and anchor checks run as always-on pre-commit hooks

`uv run python docs-dev/todo/index.py` — the boards' tables, the front matter and every `where` against the working tree — and `uv run python docs-dev/todo/anchors.py` — every architecture anchor cited in `src/` and `tests/`, and every link between the notes — run as two `language: system` hooks in `.pre-commit-config.yaml`: `ticket-boards` and `architecture-anchors`.
Both carry `pass_filenames: false` and no `files:` scope, so they run on every commit; since `ci-lint.yml` runs pre-commit, they gate CI too.

**Why.**
FEAT-25 filed the gap after BUG-49: a heading renamed through the `## The triad` → `## The quartet` change broke every citation of it, and nothing failed — no step in CI and no hook ran either sweep, so both depended on a contributor remembering the scripts exist.
The ticket leaned towards a CI step — `index.py --check`'s own docstring then called it "the form to run in CI" — and the maintainer settled on the hooks while closing it: a hook fails at commit time, where the fix is one `uv run python docs-dev/todo/index.py` away, and this repository already keeps its validity gates inside the tooling that runs every time (pre-commit, actionlint) rather than in CI-only steps.
The hooks are unscoped deliberately: a `files:` filter would spare commits that cannot touch the pattern, but the boards check also catches a commit that deletes or renames a file an open ticket's `where` names, and no fixed pattern can express "anything any ticket points at".

**The boards hook writes.**
`ticket-boards` runs `index.py` without `--check`, so a stale table is rewritten in place and the run still fails: pre-commit fails any hook that modifies a tracked file, whatever its exit code.
A contributor gets the fix along with the failure, and CI, whose checkout then differs from the commit, fails as it did under `--check`.
The script therefore needs no flag of its own to exit non-zero after a rewrite, and keeps exiting 0 for whoever runs it by hand; a validation error still exits 1 and writes nothing.
`end-of-file-fixer`, `ruff-check --fix`, `codespell --write-changes` and `rumdl --fix` in the same config rely on the same contract.

**Precedents.**
The line-endings and actionlint hooks are the same shape — a validity gate that lives in pre-commit, because that is the one tool every contributor runs ([line endings](line-endings-pinned-in-gitattributes.md), [lint holds the line](lint-holds-the-line.md)); uv on `PATH` is not a new requirement, it is what every command in `AGENTS.md` already says.

**Cost.**
Every commit pays two `uv run` startups — about seven seconds combined on a Windows laptop, most of it uv's own rather than the scripts' — and a bare checkout pays no more: both scripts skip the `.gitignore`d agent protocols, so they run on a fresh clone unchanged.

---
filed: 2026-09-29
where:
  - .github/workflows/ci-lint.yml
  - .pre-commit-config.yaml
  - docs-dev/todo/
effort: S
risk: low
impact: none
---
# FEAT-25 — Nothing in CI runs the board and anchor checks

`docs-dev/todo/index.py` validates the boards and regenerates their tables, and
`docs-dev/todo/anchors.py` (added with BUG-49) checks every `docs-dev/architecture/*.md#anchor`
cited in `src/` and `tests/`, and every link between the notes in `docs-dev/` and the protocols
(BUG-148), against the files and headings that exist. Neither runs automatically: `ci-lint.yml`
runs pre-commit only, and `.pre-commit-config.yaml` holds no local hook for either, so both depend on
a contributor remembering `--check` exists. A stale board table or a renamed heading that misses
a citation therefore survives a green CI run — BUG-49 itself went unnoticed through the whole
`## The triad` → `## The quartet` rename that caused it.

Wire both into CI or pre-commit. A CI step in `ci-lint.yml`
(`uv run python docs-dev/todo/index.py --check`, then `uv run python docs-dev/todo/anchors.py`)
matches what `index.py --check` already documents as "the form for CI"; a local pre-commit hook
fails earlier but slows every commit for checks most commits cannot break. Precedent: the repo
already keeps its validity gates inside the tools that run in CI (pre-commit, actionlint), and
`index.py --check` exists precisely for this.

*(inferred — the CI and pre-commit configuration were read, not observed failing; no
contribution flow was exercised.)*

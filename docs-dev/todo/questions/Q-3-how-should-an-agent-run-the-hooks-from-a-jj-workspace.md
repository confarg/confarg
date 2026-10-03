# Q-3 — How should an agent run the hooks from a jj workspace, where pre-commit cannot?

**Where:** `AGENTS.md` § Commands · **Filed:** 2026-10-03

A jj workspace created with `jj workspace add` carries no `.git`: the workspace this was filed
from (`confarg.1`, pointed at the main checkout's `.jj/repo`) is not inside any Git repository,
so the mandated `uv run pre-commit run --all-files` aborts at git detection, revision-independent
— it fails before reading any file, so no change can cause or fix it. Observed while closing
REF-79:

```console
$ uv run pre-commit run --all-files
An error has occurred: FatalError: git failed. Is it installed, and are you in a Git repository directory?
Check the log at C:\Users\Pascal\.cache\pre-commit\pre-commit.log
```

Agents working in a workspace are left improvising verification, and the improvised answer can
be wrong: `uv run ruff check` resolves 0.16.7, whose PLR0917 hits and Markdown formatting
disagree with the pinned hook
([REF-66](../refactors/REF-66-pinned-ruff-disagrees-with-the-project-ruff.md)). Options:

- Document a workspace-safe substitute in `AGENTS.md`: run the pinned hook tools directly on
  the changed files — `uvx ruff@0.15.16 check` and `format --check` — plus the trivia hooks.
  Exact and works from anywhere; but it re-implements the hook set, so it drifts whenever
  `.pre-commit-config.yaml` is bumped.
- Mandate running `pre-commit` from the main checkout. The real hooks; but they inspect the
  main working copy, not the workspace's files, so they verify nothing about the change in
  flight.
- Declare workspaces the contributor's own business, outside the protocol's scope, as
  `docs-agents/README.md` already does for how an agent is driven. No protocol churn; but
  every workspace-bound agent keeps improvising, with the wrong-pinned ruff as the likely
  default.

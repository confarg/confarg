# REF-66 — the pinned ruff and the project's own ruff disagree

**Where:** `.pre-commit-config.yaml` · **Filed:** 2026-09-28
**Effort:** S · **Risk:** low · **Impact:** none

The `ruff-pre-commit` hook pins v0.15.16 while the project environment resolves ruff 0.16.7, and
the newer one reports 17 `PLR0917` ("too many positional arguments") errors the hook does not
(16 at filing). Its formatter disagrees too: 0.16 formats
the Python code blocks inside Markdown, and wants to reformat ten of them — `README.md`, two
`docs/how-to/` pages and seven board tickets — that 0.15.16 leaves alone. So `uv run ruff check .`
fails on an otherwise clean tree while `uv run pre-commit run --all-files` passes, which makes the
local command untrustworthy and turns the next hook bump into a 17-site lint change plus a
ten-file markdown reformat landing on top of whatever else is in flight.

Either bump the hook and settle `PLR0917` now — the sites already carry `# noqa: PLR0913` with a
rationale, so most want the second code added to the same comment, keeping the line under 120
characters or ruff reformats and drops the suppression — or pin the project's ruff to the hook's
version so one answer comes out of both.

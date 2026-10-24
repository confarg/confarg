# The ruff hook and the dev dependency carry one pin

`ruff` rides in the dev dependency group, pinned `==` to the exact version the `ruff-pre-commit` hook's rev names, and a bump moves both in one revision.
Before this, the hook alone pinned a ruff: the project carried none, so `uv run ruff check .` resolved whatever `ruff` sat on the machine's `PATH` — 0.16.7 here — and reported `PLR0917` hits and Markdown reformats the hook's 0.15.16 knew nothing of.
The local command and the hook disagreed on a clean tree, which is what REF-66 was filed on.

Why a second pin instead of the hook alone: `uv run <tool>` falls through to `PATH` for a tool the project does not carry, so a hook-only pin leaves the local command answering to whatever the machine happens to have installed.
Why a remote hook plus a dev pin, and not a `repo: local` hook running `uv run ruff` — which would single-source the version, the way `ticket-boards` and `architecture-anchors` run: ruff-pre-commit gives the hook an isolated install of its own, so linting a revision never depends on the working copy's venv being synced, and `pre-commit autoupdate` still names the next rev.
Cost: two pins that must move together, and a hook bump that wants its lint sites and Markdown blocks settled in the same revision — the 0.16.9 bump added `PLR0917` to the fourteen `PLR0913` noqa lists ([a lint rule is enabled, not hand-fixed](lint-holds-the-line.md#a-lint-rule-is-enabled-not-hand-fixed-once)) and landed the fourteen-file Markdown reformat ([quoted code keeps the formatter's spacing](quoted-code-keeps-formatter-spacing.md#quoted-code-keeps-the-formatters-spacing)), since the formatter-era `ruff-format` hook covers Markdown.

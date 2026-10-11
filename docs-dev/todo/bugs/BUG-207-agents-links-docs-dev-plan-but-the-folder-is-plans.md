---
filed: 2026-10-08
where:
  - AGENTS.md  # line 11, the Documentation section's fourth bullet
effort: S
risk: low
impact: none
severity: trivial  # close call: the always-non-zero sweep masks a future genuine error, but no library user meets it
introduced_by: unknown  # agent files are unversioned, so no revision to name; searched the snapshot archive — the docs-dev/plan/ link first appears in the 2026-10-07 23:28 zip, five days after PR-210 created the folder as plans/
---
# BUG-207 — AGENTS.md links docs-dev/plan/, a folder that has been plans/ since PR-210

The Documentation section of `AGENTS.md` routes its fourth bullet to `docs-dev/plan/README.md`, but the folder is `docs-dev/plans/` — `docs-dev/README.md` and the folder itself carry the plural. The anchors sweep follows `AGENTS.md`'s links too, so it exits non-zero on every run, and a run that finds a genuine stale citation is indistinguishable from a run that finds only this. Fix direction: relink to `plans/`, which the section's other bullets already spell correctly.

Origin: the Documentation section was rewritten on 2026-10-07 — agent files are unversioned and archived as snapshots outside the repository, and the `docs-dev/plan/` link first appears in the 2026-10-07 23:28 snapshot — five days after PR-210 created the folder as `plans/`, so the link never resolved: latent, not a regression.

```console
$ uv run python docs-dev/todo/anchors.py
error: AGENTS.md:11: links docs-dev/plan/README.md, but there is no such file
$ ls docs-dev/plans/README.md
docs-dev/plans/README.md
# expected: the bullet names the folder that exists and the sweep passes
# actual:   the sweep errors on every run, naming a folder that never existed
```

---
filed: 2026-10-08
where:
  - docs-dev/
  - docs-agents/
effort: M
risk: low
impact: none
severity: trivial
---

# REF-91 — The documentation written before the no-hard-wrap rule is still hard-wrapped

`AGENTS.md`'s "Writing documentation" section bans hard-wrapping: line breaks belong at the end of a coherent paragraph, not mid-sentence.
Files written since the rule follow it — the tickets filed this week and `AGENTS.md` itself are unwrapped — but most of the older tree still breaks sentences at roughly 100 columns: `docs-dev/README.md`, `docs-dev/todo/README.md`, the architecture notes, the plans, and the protocols in `docs-agents/`.
Fix direction: reflow each paragraph to one line, file by file — or settle the rule as reflow-as-touched and record that, so the tree and the rule stop disagreeing.

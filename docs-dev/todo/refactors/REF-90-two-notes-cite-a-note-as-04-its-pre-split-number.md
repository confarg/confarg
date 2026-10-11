---
filed: 2026-10-08
where:
  - docs-dev/architecture/cli-parsing/token-consumption.md  # line 47
  - docs-dev/architecture/environment-parsing.md  # line 57
effort: S
risk: low
impact: none
severity: trivial
---
# REF-90 — Two notes cite a note as `[04]`, its number from before the folder split

Two architecture notes spell a citation's link text `[04]` — the number `cli-adapters` carried as `04-cli-adapters.md` before the numbered notes were split into topic folders. PR-238 rewrote both links' targets to `cli-adapters/whole-value-flags.md` but kept the stale texts, which read as a numbering the notes no longer carry; the sweep follows link targets, not texts, so nothing flags them. Fix direction: spell the topic as the text, as every other cross-note citation does.

- `token-consumption.md`: "the adapters must register and decode the same bare flags ([04](../cli-adapters/whole-value-flags.md#whole-value-flags))"
- `environment-parsing.md`: "CLI whole-value flag consults ([04](cli-adapters/whole-value-flags.md#whole-value-flags))"

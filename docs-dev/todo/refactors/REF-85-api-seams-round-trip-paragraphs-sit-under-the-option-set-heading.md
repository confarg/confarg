---
filed: 2026-10-04
where:
  - docs-dev/architecture/pipeline/api-seams.md
effort: S
risk: low
impact: none
severity: trivial
---
# REF-85 — `api-seams.md`'s round-trip paragraphs sit under the option-set heading

[pipeline/api-seams.md](../../architecture/pipeline/api-seams.md#public-api-seams) has a single
`##` heading, `One option set` (line 16), and the round-trip rationale that follows it —
"Round-trip fidelity comes from the seam" (line 50), "A coerced leaf therefore round-trips at
`build()`" (line 63), and the `dump()` dataclass-only rule after them — is not about the option
set at all. With no heading of its own, nothing can link that rationale precisely: the
design decisions and tickets that rely on it link the whole note (`#public-api-seams`), and a
link to `#one-option-set` would land a reader in the wrong argument. Fix direction: give the
round-trip paragraphs their own `##` heading (keeping `One option set` as it is, since
`src/confarg/_defaults.py` cites it), then repoint the links that mean the round trip, such as
[dump-round-trips-at-the-built-object.md](../../architecture/design-decisions/dump-round-trips-at-the-built-object.md#dump-round-trips-at-the-built-object)
and the untyped-rewriter plan's two citations.

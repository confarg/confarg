---
filed: 2026-09-12
effort: L
risk: medium
impact: behavior
needs_design: true  # the effort sizes the design pass; the implementation is not sized
---
# FEAT-6 — `Annotated` field metadata read by all three channels

Help text, aliases and per-field options without requiring a custom type on user data
structures. Must land in files, environment and CLI at once.

Field-level **aliases** belong here too: accept both an old and a new name for a field and warn on
the old. They arrived from FEAT-11, whose heavier half (a declared schema version and a migration
chain) was absorbed by
[FEAT-23](FEAT-23-post-resolve-transform-layer.md). Aliases are the separable, lighter answer to the
same problem — renaming a field without breaking every configuration in the wild — and they need no
version key, no migration stage and no ordering story, only `Annotated` metadata all three channels
read. Precedents at that end of the scale: serde's `#[serde(alias)]` and pydantic-settings'
`AliasChoices`, neither of which has a version concept. Worth doing first, and alone.

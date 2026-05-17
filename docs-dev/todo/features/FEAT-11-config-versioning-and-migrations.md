# FEAT-11 — Configuration versioning and a migration registry

**Where:** new module, plus a hook in the merge pipeline · **Filed:** 2026-09-12
**Effort:** XL · **Risk:** high · **Impact:** config

Renaming or moving a field today breaks every configuration file, environment variable and
command-line flag in the wild, and confarg has nothing to say about it. A registry would: a
configuration declares its schema version (`version: 2` as a reserved file key, or an implicit
version 1), the program registers migrations, and confarg applies the chain from the declared
version up to the current one before the data reaches `build()`. The operations worth having
declaratively — rename, move a key to another path, split, merge, drop with a deprecation
warning — cover the common cases; an escape hatch taking an arbitrary dict-to-dict function
covers the rest.

Design axes to settle: **where migrations run** — per source before the deep merge (each file
migrated on its own terms, so an old file and a new one still merge correctly) or once on the
merged dict (simpler, but a single version key cannot describe a stack of files of different
vintages). **Parity**, the hard part: a renamed field renames its environment variable and its
CLI flag too, so a migration has to apply to all three channels, not just files — a
file-only migration is exactly the silent divergence
[09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)
forbids. **Footprint**: field-level aliases (accept both old and new name, warn on the old) are
the lighter half of this and need no version key at all — they are `Annotated` metadata, see
FEAT-6, and may be worth doing first and alone. **Tooling**: a `confarg migrate` subcommand
that rewrites a file in place, alongside FEAT-9 and FEAT-10 on the same console script;
`dump_file()` already writes configurations back out.

Precedents, since each picked a different point on this scale: Terraform has `moved` blocks
for renamed resources and a `required_version` constraint; Cargo gates behavior on an
`edition` key with `cargo fix --edition` to migrate; Kubernetes pairs an `apiVersion` field
with conversion webhooks between versions; Hydra's `version_base` gates its own behavior
changes but leaves user-config migration manual; ESLint ships a one-shot codemod rather than a
registry; serde and pydantic-settings stop at field aliases (`#[serde(alias)]`,
`AliasChoices`) with no version concept. The declarative-ops-plus-version-chain shape is the
Kubernetes/Terraform end; the alias-only shape is the serde end.
See [01-pipeline-and-contracts.md#the-single-merge-pipeline](../../architecture/01-pipeline-and-contracts.md#the-single-merge-pipeline).

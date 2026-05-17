# REF-59 — Two `type` blocks under `examples/` wait on the hook; the rest is generated

**Where:** `examples/6_unions/README.md`, `examples/9_child_configurations/README.md` ·
**Filed:** 2026-09-25, body updated 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

The 2026-09-25 sweep found twenty hand-copied `python` and `yaml` blocks under `examples/`.
Every one is resolved except the two `type Config = …` blocks: their sources exist
(`myapp.py`, `db_or_api.py`), but the pinned `markdown-code-snippet` hook cannot name a
`type` statement — filed upstream as FEAT-6 in that repository. Once a release carrying it
is pinned in `.pre-commit-config.yaml`, annotate both blocks with `#Config`, confirm the
hook rewrites them unchanged, and delete this ticket.

The blocks that stay hand-copied for good — bare expressions quoted out of a function,
staged teaching variants, and the run-time-written `saved_config_*.yaml` — are recorded in
[quoted-blocks-stay-hand-copied.md](../../architecture/design-decisions/quoted-blocks-stay-hand-copied.md#some-quoted-blocks-stay-hand-copied),
not tracked here. The `90_integration` blocks remain BUG-46.

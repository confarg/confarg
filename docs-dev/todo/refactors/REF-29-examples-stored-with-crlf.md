# REF-29 — Every file under `examples/` is stored with CRLF

**Where:** `examples/**` (237 files), `.pre-commit-config.yaml` (`mixed-line-ending`)
**Effort:** S · **Risk:** low · **Impact:** none

The repository is LF everywhere except `examples/`, where all 237 tracked text files are stored
with CRLF. The `mixed-line-ending` hook runs with `--fix=lf`, so every
`uv run pre-commit run --all-files` rewrites all 237 of them and a contributor who runs the hook
the way [AGENTS.md](../../../AGENTS.md) prescribes ends up with 237 whole-file diffs beside the
change they actually made — the same "the gate starts out red" problem as
[REF-28](REF-28-examples-fail-ruff.md), but noisier, because the fix is applied automatically
and has to be undone by hand.

Fix direction: convert the 237 files to LF in one revision of its own, so the next
`--all-files` run is clean. Whether a `.gitattributes` should also pin the answer is the open
part — the repository has none today, and adding one is a separate decision from converting
what is there.

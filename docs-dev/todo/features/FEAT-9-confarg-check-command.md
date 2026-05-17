# FEAT-9 — A `confarg check` command to validate a configuration against a target

**Where:** new console script (no `[project.scripts]` entry exists yet) · **Filed:** 2026-09-12
**Effort:** L · **Risk:** low · **Impact:** behavior

In a project environment, `confarg check module.Config -- --config app.yaml --db.port 5433`
should run the same pipeline `confarg.load()` runs — every channel, not a single file — resolve
the `${...}` expressions, construct the target, then report each error with its key path and
exit non-zero. A lint step for CI and editors, without writing a throwaway script. It must take
the whole argument vector because a configuration file is allowed to be partial: the keys it
omits may be supplied by the environment or on the command line, so checking the file alone
would report failures that never occur in the real run. `_import_dotted` already resolves
`module.Config` and `load()` already does the work, so the command is mostly argument plumbing
plus error formatting.

Open before this becomes work: whether "correctly formatted" means the whole `merge` →
`resolve` → `build` pipeline or stops before construction (side-effect-free validation, cf.
FEAT-5); how the command learns the `load()` keywords the calling program passes in code —
`env_prefix` above all, see FEAT-10, which has the same problem; and that importing
`module.Config` executes user code, so the command is not safe on untrusted input.
See [01-pipeline-and-contracts.md#merge-build-contract](../../architecture/01-pipeline-and-contracts.md#merge-build-contract).

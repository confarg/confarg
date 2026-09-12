# Features

Missing behavior worth having, and ideas not yet vetted. See [README.md](README.md) for the
ticket format. Anything accepted or rejected here leaves a decision in
[../architecture/10-design-decisions.md](../architecture/10-design-decisions.md).

## Gaps

### FEAT-1 — Uneven shell-completion coverage

**Where:** `src/confarg/cli/argparse/_completion.py`, `src/confarg/cli/click/_completion.py` ·
**Filed:** 2026-09-12

argparse (argcomplete) and click have completion helpers; cyclopts has none. Click completion
covers bash and zsh, not fish. Completion is the one place where per-framework divergence may
turn out to be acceptable — decide that explicitly rather than by omission.
See [04-cli-adapters.md](../architecture/04-cli-adapters.md).

### FEAT-2 — Protocol-typed callables and `**kwargs`

**Where:** `src/confarg/_callable.py` · **Filed:** 2026-09-12

Callable specs bind against a concrete signature. A field typed as a `Protocol` with
`__call__`, or a target accepting `**kwargs`, has no story yet: decide whether extra keys bind
as keyword arguments and how they are validated.
See [06-callables.md](../architecture/06-callables.md).

### FEAT-9 — A `confarg check` command to validate a config file against a target

**Where:** new console script (no `[project.scripts]` entry exists yet) · **Filed:** 2026-09-12

In a project environment, `confarg check module.Config config.yaml` should load the file,
resolve its `${...}` expressions and construct the target, reporting each error with its key
path and exiting non-zero — a lint step for CI and editors, without writing a throwaway
script. `_import_dotted` already resolves `module.Config` and `load()` already does the work,
so the command is mostly argument plumbing plus error formatting.

Open before this becomes work: whether "correctly formatted" means the whole `merge` →
`resolve` → `build` pipeline or stops before construction (side-effect-free validation, cf.
FEAT-5); how the environment and CLI channels are represented, since only the file channel can
be checked statically — a parity divergence needing explicit approval; whether several files
may be passed to check the merged result; and that importing `module.Config` executes user
code, so the command is not safe on untrusted input.
See [01-pipeline-and-contracts.md#merge-build-contract](../architecture/01-pipeline-and-contracts.md#merge-build-contract).

## Unvetted ideas

Carried over from an earlier architecture review. None is decided; each needs a design pass
before it becomes work.

### FEAT-3 — A registry of reserved sentinel keys

`__root__`, `__cast__`, `__value__`, `__include__`, `+`, `-`, `*`, `~` are recognised in
several places. One registry, plus a guard against user keys colliding with them, would harden
the plain-dict IR. See [01-pipeline-and-contracts.md#deep-merge-semantics](../architecture/01-pipeline-and-contracts.md#deep-merge-semantics).

### FEAT-4 — An explicit ordered patch-op stream

Vanilla and the adapters agree on collection patches because the adapters re-run the vanilla
parse loop in `patch_only` mode. An ordered stream of patch operations, produced once and
consumed by both, would make that parity structural instead of behavioral.
See [04-cli-adapters.md#collection-patch-parity](../architecture/04-cli-adapters.md#collection-patch-parity).

### FEAT-5 — Optional structural validation right after `merge()`

Errors would surface earlier and closer to their source, without changing the
merge/build contract (`merge()` stays unvalidated by default).
See [01-pipeline-and-contracts.md#merge-build-contract](../architecture/01-pipeline-and-contracts.md#merge-build-contract).

### FEAT-6 — `Annotated` field metadata read by all three channels

Help text, aliases and per-field options without requiring a custom type on user data
structures. Must land in files, environment and CLI at once.

### FEAT-7 — Lazy resolution between `merge` and `build`

For very large configurations, resolve only the branches actually constructed.

### FEAT-8 — Value provenance

Remember which source set each value (as Dynaconf's `inspect` does), as an opt-in richer IR.
Useful for `--help`-time explanations and for debugging precedence surprises.

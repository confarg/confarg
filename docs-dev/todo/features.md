# Features

Missing behavior worth having, and ideas not yet vetted. See [README.md](README.md) for the
ticket format. Anything accepted or rejected here leaves a decision in
[../architecture/10-design-decisions.md](../architecture/10-design-decisions.md).

## Gaps

### FEAT-1 — Uneven shell-completion coverage

**Where:** `src/confarg/cli/argparse/_completion.py`, `src/confarg/cli/click/_completion.py` ·
**Filed:** 2026-09-12
**Effort:** L · **Risk:** low

argparse (argcomplete) and click have completion helpers; cyclopts has none. Click completion
covers bash and zsh, not fish. Completion is the one place where per-framework divergence may
turn out to be acceptable — decide that explicitly rather than by omission.
See [04-cli-adapters.md](../architecture/04-cli-adapters.md).

### FEAT-2 — Protocol-typed callables and `**kwargs`

**Where:** `src/confarg/_callable.py` · **Filed:** 2026-09-12
**Effort:** L · **Risk:** medium

Callable specs bind against a concrete signature. A field typed as a `Protocol` with
`__call__`, or a target accepting `**kwargs`, has no story yet: decide whether extra keys bind
as keyword arguments and how they are validated.
See [06-callables.md](../architecture/06-callables.md).

### FEAT-9 — A `confarg check` command to validate a configuration against a target

**Where:** new console script (no `[project.scripts]` entry exists yet) · **Filed:** 2026-09-12
**Effort:** L · **Risk:** low

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
See [01-pipeline-and-contracts.md#merge-build-contract](../architecture/01-pipeline-and-contracts.md#merge-build-contract).

### FEAT-10 — A `confarg explain` command showing the final configuration and each value's origin

**Where:** new console script, shared with FEAT-9 · **Filed:** 2026-09-12
**Effort:** XL *(depends on FEAT-8)* · **Risk:** low

`confarg explain module.Config -- --config app.yaml --db.port 5433` takes the same argument
vector as `confarg check` and prints the merged, resolved configuration with, for every leaf,
where its value came from: which config file (and which key in it), which environment variable,
which command-line argument, or the target's own default. That is the answer to "why is this
value what it is" — precedence surprises, a file silently overridden by a stale environment
variable, an expression resolving to something unexpected — and it is the same question
`--help`-time explanations need. It depends on FEAT-8: the plain-dict IR remembers no source
today, so provenance has to exist before it can be printed.

Passing `env_prefix` is the open problem, and it is not specific to this command. The prefix is
a `load()` keyword the calling program sets in code, so a standalone tool cannot know it, yet
without it the environment channel is either off or guessed. Options: an explicit tool flag
(`--env-prefix APP_`, which needs a `--` separator so it cannot collide with a user field of
the same name), a `[tool.confarg]` table in `pyproject.toml`, declaring it on the target type,
or pointing the tool at the program's own `load()` call site instead of at the target. The same
choice governs every other keyword the tool would otherwise have to guess (`union_tag`,
`config_files`, `TagPolicy`), so settle it once for both commands.
See [02-files-and-env.md#environment-parsing](../architecture/02-files-and-env.md#environment-parsing).

### FEAT-11 — Configuration versioning and a migration registry

**Where:** new module, plus a hook in the merge pipeline · **Filed:** 2026-09-12
**Effort:** XL · **Risk:** high

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
[09-invariants.md#cross-channel-parity](../architecture/09-invariants.md#cross-channel-parity)
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
See [01-pipeline-and-contracts.md#the-single-merge-pipeline](../architecture/01-pipeline-and-contracts.md#the-single-merge-pipeline).

### FEAT-12 — Carefully scoped expression expansion

**Where:** `src/confarg/dictexpr/_expressions.py` (`_ALLOWED_NODES`, the call whitelist) ·
**Filed:** 2026-09-12
**Effort:** L *(list literals alone; XL with dict and set literals)* · **Risk:** high

The safety model forbids list/dict/set literals, slices, comprehensions, lambdas, f-strings
and `}` inside an expression
([07-expressions.md#safety-model](../architecture/07-expressions.md#safety-model)). That is a
sound default, but it leaves expressions unable to say ordinary things —
`${[host, backup_host]}`, `${list(hosts) + [fallback]}`, `${sorted(ports)}`. A conservative
expansion — list and dict literals plus a fixed set of builtin conversions (`list`, `tuple`,
`dict`, `set`, `sorted`, `sum`, `any`, `all`) added to the existing free-function whitelist —
would meaningfully increase expression power **without touching `eval`**: the interpreter
still walks a whitelisted AST, and each new node has a small, total evaluation rule.

The coupling is explicit and decides the order of work. `_Prefixer` rewrites only `ast.Name`
bases, and that is correct *only* because no binding construct is whitelisted, so every
non-function `Name` is a reference base; **adding a binding construct — a comprehension or a
lambda — breaks reference prefixing** and requires reworking `_Prefixer` to carry a scope
([07-expressions.md#reference-anchoring](../architecture/07-expressions.md#reference-anchoring),
[09-invariants.md#fragile-couplings](../architecture/09-invariants.md#fragile-couplings)). List
literals bind nothing, so they are the safer first step and can land on their own. Two further
constraints: dict and set literals need `}` inside the expression, which the `${...}` regex
forbids, so they additionally require brace-balanced or lexical delimiter scanning — another
reason lists come first; and `sorted(key=...)` is off the table for as long as lambdas are,
so the added builtins take no callable arguments.

Parity is not at risk — the engine is shared by all three channels and all four front-ends, so
an expansion lands everywhere at once — but each new node must stay inside the deferral rule
([07-expressions.md#deferral-rule](../architecture/07-expressions.md#deferral-rule)): a value
gate must still defer on `contains_expression`, and a literal that now resolves to a `list`
must reach `build()` as a list rather than being coerced early. Shell quoting of `[`/`]` is a
documentation matter, not a divergence.

Precedents: Bicep and CUE allow literals and a curated standard library with no general
evaluation; Jsonnet and Nix go all the way to a full functional language; Home Assistant and
Ansible hand config templating to Jinja2 and accept arbitrary-expression risk; OmegaConf
(Hydra) stays at interpolation plus registered resolver functions, closest to where confarg
is now. The curated-literals-and-builtins point is the Bicep/CUE end, reachable without
adopting a language.

## Unvetted ideas

Carried over from an earlier architecture review. None is decided; each needs a design pass
before it becomes work.

### FEAT-3 — A registry of reserved sentinel keys

**Effort:** S *(design pass; implementation not sized)* · **Risk:** high

`__root__`, `__cast__`, `__value__`, `__include__`, `+`, `-`, `*`, `~` are recognised in
several places. One registry, plus a guard against user keys colliding with them, would harden
the plain-dict IR. See [01-pipeline-and-contracts.md#deep-merge-semantics](../architecture/01-pipeline-and-contracts.md#deep-merge-semantics).

### FEAT-4 — An explicit ordered patch-op stream

**Effort:** M *(design pass; implementation not sized)* · **Risk:** high

Vanilla and the adapters agree on collection patches because the adapters re-run the vanilla
parse loop in `patch_only` mode. An ordered stream of patch operations, produced once and
consumed by both, would make that parity structural instead of behavioral.
See [04-cli-adapters.md#collection-patch-parity](../architecture/04-cli-adapters.md#collection-patch-parity).

### FEAT-5 — Optional structural validation right after `merge()`

**Effort:** S *(design pass; implementation not sized)* · **Risk:** low

Errors would surface earlier and closer to their source, without changing the
merge/build contract (`merge()` stays unvalidated by default).
See [01-pipeline-and-contracts.md#merge-build-contract](../architecture/01-pipeline-and-contracts.md#merge-build-contract).

### FEAT-6 — `Annotated` field metadata read by all three channels

**Effort:** L *(design pass; implementation not sized)* · **Risk:** medium

Help text, aliases and per-field options without requiring a custom type on user data
structures. Must land in files, environment and CLI at once.

### FEAT-7 — Lazy resolution between `merge` and `build`

**Effort:** M *(design pass; implementation not sized)* · **Risk:** high

For very large configurations, resolve only the branches actually constructed.

### FEAT-8 — Value provenance

**Effort:** M *(design pass; implementation not sized)* · **Risk:** high

Remember which source set each value (as Dynaconf's `inspect` does), as an opt-in richer IR.
Useful for `--help`-time explanations and for debugging precedence surprises.

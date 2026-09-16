# FEAT-10 — A `confarg explain` command showing the final configuration and each value's origin

**Where:** new console script, shared with FEAT-9 · **Filed:** 2026-09-12
**Effort:** XL *(depends on FEAT-8)* · **Risk:** low · **Impact:** behavior

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
See [02-files-and-env.md#environment-parsing](../../architecture/02-files-and-env.md#environment-parsing).

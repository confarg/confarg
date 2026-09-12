# Pipeline and contracts

## The pipeline

```
argv  ──▶ _parse_cli ─┐                        build()
env   ──▶ _parse_env ─┼─▶ _merge_sources ─▶ resolve_expressions ─▶ strip locals ─▶ construct ─▶ T
files ──▶ _files ─────┘   (_pipeline.py)      (dictexpr)                           (typedload)
                          config < env < CLI
```

`load()` = `merge()` + `build()`. `build()` = `resolve_expressions` + `_strip_locals` +
`typedload.construct` (with `__root__` unwrapping for non-struct targets).

## Plain dicts as the intermediate representation

Every stage before construction produces and consumes plain nested `dict`s. There are two
intermediate representations, both plain dicts:

1. the **merged dict** — the union of all sources, `${...}` still literal (`merge()`);
2. the **resolved dict** — same shape, expressions evaluated (`resolve()`).

Why: it makes the API decomposable (stop, inspect, persist or hand-assemble at any seam),
keeps the engines independent of where data came from, makes round-tripping trivial, and
lets the contract tests assert byte-equality across front-ends.

Cost: the dict is untyped and stringly keyed, so structural mistakes surface late (in
`build()`), and sentinel keys (`__root__`, `__cast__`, `+`, `-`, `*`, `~`, …) live in the same
key space as user data. See [FEAT-3](../todo/features.md).

## Public API seams

The API is the pipeline turned inside out; `__all__` in `confarg/__init__.py` groups it
deliberately (non-alphabetical, hence `noqa: RUF022`):

| Group | Functions | Stops after |
|---|---|---|
| two-step | `merge`, `build` | collection / resolution + construction |
| three-step (dict-centric) | `merge`, `resolve`, `from_dict` | collection / resolution / construction |
| one-step | `load` | everything |
| dump | `dump`, `dump_file` | serialization |

Shared keyword defaults live in `_defaults.py` so the four front-ends cannot drift.

**Round-trip fidelity comes from the seam, not from a reverse pass.** `merge()` keeps
`${...}` verbatim and `dump_file(raw_dict, path)` writes it back (only unwrapping
`_StrToken`), so a merged config can be saved with its expressions. `dump(instance)`
serializes the *constructed* object and therefore emits resolved values. There is
deliberately no "un-resolve" step.

`dump()` accepts dataclass instances only; plain classes cannot be dumped reliably (their
state is not guaranteed to mirror `__init__`), so the error message steers users to dumping
the merged dict instead.

## Merge build contract

`merge()` returns an **unvalidated** dict: it is not guaranteed to be constructible into the
target. Convertibility is decided only in `build()`/`construct()`, which raise
`TypeCoercionError`/`MissingFieldError`.

- Parsers reject only what they can **prove wrong at parse time** (a flag missing its value,
  an empty `--flag` for a union whose only sequence variant is a fixed tuple, invalid JSON
  after an explicit `.json` cast). A config file or env var carrying `"abc"` for an `int`
  merges cleanly and fails in `build()`.
- **Do not add convertibility validation to the merge layer.** It would make channels
  disagree (a CLI check that env/files skip) and it cannot see expression results.
- The merge layer is **type-unaware; `build()` is type-aware.** When the right behavior
  depends on the type, the merge layer defers instead of guessing:
  - an index patch past the end of a base list (`--input.2 3` over `[1, 2]`) is an error for a
    `list` but fills a slot for a fixed `tuple`, so `_merge_list_base` carries the base as
    `{"*": base, "2": 3}` and lets construction decide;
  - `_parse_env._match_union_part` returns a field type only when all union variants agree,
    otherwise `None` (store the raw token, coerce in `construct`).
- Expressions are the extreme case: their value is unknown until `build()`. See
  [07-expressions.md](07-expressions.md#deferral-rule).

## Source precedence

```
config files  <  environment variables  <  command-line arguments
```

All config files share the lowest level. Within it, later files win:

1. `files=` in the order given;
2. `env_config` — the one file named by that environment variable;
3. `<PREFIX>CONFIG[__SUBPATH]` pointers, **sorted by variable name**, which sorts by subpath
   depth: the global file first, then `CONFIG__DB`, then `CONFIG__DB__HOST`, so a more
   specific file overrides a broader one regardless of environment iteration order;
4. CLI `--config[.subpath][+]` in left-to-right argv order.

Environment variables are parsed *inside* the pipeline (not before it) because they can
name config files that must be loaded at step 3, before inline env values are applied.

## The single merge pipeline

`_pipeline._merge_sources` is the only implementation of source priority, file-loading
order, locals checks and final reference canonicalization. `confarg.merge()` and the three
adapters' `merge_*` functions each extract their CLI values and `--config` pairs their own
way, then delegate here.

**Rule: fix merge-order or file-loading behavior in this module only.** It then lands in
all front-ends at once.

History: before PR #65 each adapter re-implemented parts of the pipeline and diverged
(custom `config_flag` ignored for env pointers, trailing `+` ignored, `env_config`
unsupported, env config files unsorted, `construct()` called without `__root__`
unwrapping). `TestPipelineParity` in `tests/cli/test_backend_contract.py` pins each of those.

## Deep merge semantics

`_merge._deep_merge(base, override)` is recursive, **dict-wins**: the override replaces
anything that is not a dict-on-dict, which is merged recursively.

- **A union tag in the override discards the base entirely.** Naming a class says "this is
  a new object", so fields of the previous variant must not leak in (the README's
  `--class myapp.SQLiteConfig --dbpath …` over a server config).
- `DICT_DELETE` (from `key-` in files, `--field.key-`, `FOO__KEY-`) removes a key.
- File-sourced shorthand `key+:` / `key-:` / `"N-":` is normalized to sentinels by
  `_normalize_merge_ops` so files, env and CLI share one patch vocabulary.

List patches travel as a dict of sentinel keys:

| Key | Meaning | Produced by |
|---|---|---|
| `"+"` | append items | `--f+`, `key+:`, `--config.<f>+` |
| `"-"` | delete original indices (before appends) | `--f.N-`, `"N-":`, `F__N-` |
| `"*"` | replacement base list | a whole-list value followed by a patch in the same source, or a deferred index patch |
| `"~"` | delete indices *after* appends | `--f.N-` appearing after `--f+` on the CLI |
| `"N"` | index patch (negative counts from the end) | `--f.N`, `F__N`, index-keyed dicts |

`_apply_list_ops` applies them in a **fixed semantic order** (pre-append deletes, appends,
post-append deletes, index patches) so the result never depends on dict iteration order.
`"*"` exists so a replacement followed by a patch in the same source is not lost when the
patch merges; `"~"` exists so an index typed after an append refers to the post-append list.
An index patch recurses through `_merge_existing_value`, the one "combine existing with
override" dispatcher, so patches compose at any depth.

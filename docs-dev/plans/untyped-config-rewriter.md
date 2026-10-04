# Plan — A model-less configuration rewriter for confarg

**Drafted:** 2026-09-26 · **Subject:** an app that composes configuration files, applies env/CLI
overrides and writes one file back to disk, with no target type · **Status:** proposal, not approved

## Context

confarg loads configuration from files, environment variables and command-line arguments and
*constructs a typed object* from it. The want here is the same front half with a different back
half: load and compose one or several configuration files exactly the way confarg does, apply
env/CLI overrides, and **write the result back to disk as a single file** — with no target type,
no schema, no model.

Three findings shape the design:

1. **confarg already documents this workflow.** `_api.py:199` (`resolve()`) has it in its own
   docstring: `merge()` → `resolve()` → `dump_file()`. The architecture states the split
   explicitly: *"The merge layer is type-unaware; `build()` is type-aware"*
   (`docs-dev/architecture/pipeline/README.md:81`), with plain dicts at every seam.
2. **The reusable core is already import-isolated.** `_merge.py` (445 lines) imports nothing but
   `exceptions`; `dictexpr/_expressions.py` (1081) likewise; `_files.py` (534 — format dispatch,
   `__include__`, mounting) depends only on `_merge`, `dictexpr` and the `_StrToken` class. With
   `_cast.py`, `_defaults.py` and `exceptions.py` that is ~2.6k lines of stdlib-only, schema-free
   compose/merge/interpolate machinery reusable verbatim.
3. **A model-less override subsystem already exists: the `locals:` layer.**
   `_pipeline._apply_locals_overrides` / `_coerce_override` (`_pipeline.py:120-179`) take env and
   CLI overrides and coerce each to *the runtime type of the value the file declared*, with full
   env/CLI parity and typo detection (`docs-dev/architecture/locals.md:50`). This tool is that
   idea generalised: **the composed document is the model.**

Model-awareness is concentrated in exactly two places this tool cannot reuse — `_parse_env.py`
(441) and `_parse_cli.py` (1191), which consult the target for key casing, flag arity,
container-vs-scalar and leaf coercion — plus `typedload/`, `_serialize.py`, `_callable.py`,
`_tags.py` and `cli/` (~4.8k lines of adapters).

### Decisions taken

| Decision | Choice |
|---|---|
| Packaging | **Inside the confarg distribution**, as `confarg.untyped` plus the project's first console script. *(Recommendation — the one item worth revisiting; alternatives were a dependent package or extracting `confarg-core`.)* |
| Value typing | Coerce to the type of the existing value in the document; YAML-style scalar resolution for keys not in it; explicit casts always win. |
| Write fidelity | ruamel.yaml / tomlkit behind an optional extra, falling back to confarg's `yaml.dump`/`tomli_w`/`json` writers. |
| Unknown keys | Strict by default (error, as `LocalsError.not_declared` does), `--allow-new` to opt in. |

Why one distribution rather than a separate library: the composition semantics must not fork
(`docs-dev/architecture/pipeline/README.md:116` — "fix merge-order or file-loading
behavior in this module only"), the shared surface is most of what the tool needs, confarg is at
0.0.4 with **no `[project.scripts]` at all**, and FEAT-9/FEAT-10 already plan
`confarg check` / `confarg explain` on one console script. Extracting `confarg-core` stays
possible later — but the core's true boundary is unknowable until a model-less parser exists.

### Alternatives considered and rejected

- **A fully independent library.** Would reimplement `__include__` layering, subpath mounting,
  the `+ - * ~ N` patch sentinels and the expression engine — ~2.6k lines of proven logic — and
  the two tools' composition semantics would drift apart.
- **A separate package depending on confarg.** Pins the new tool to confarg's *private* internals
  (`_files`, `_merge`, `dictexpr`) or forces premature widening of the public API.
- **Extracting `confarg-core` up front.** Cleanest boundary in principle, most churn, and the
  boundary cannot be drawn correctly until model-less env/CLI parsing exists.
- **Off the shelf instead of building.** `anyconfig_cli`, OmegaConf, `yq`, `dasel`,
  `config-merge`, Dynaconf's CLI, and ytt/CUE/jsonnet all cover parts of this. None has confarg's
  composition vocabulary (`__include__` at any node with list layering and cycle detection,
  subpath mounting, the list-patch sentinels, anchored `${...}` references), which is the reason
  to build rather than adopt.

---

## The one real architectural change: load files *first*

confarg parses env before loading files, because env vars can name config files
(`_pipeline.py:320-334`, rationale at `docs-dev/architecture/config-files/README.md` and
`01-pipeline-and-contracts.md:106`). This tool needs the opposite: the document must exist before
env/CLI parsing, because the document *is* the source of key casing and types.

Resolved with a two-phase scan, so no ordering guarantee is lost:

```
argv ─┬─▶ scan for --config[.sub][+] only ─┐
env  ─┴─▶ scan for CONFIG[__SUB] only    ──┼─▶ _files: load + __include__ + mount + deep-merge
files ────────────────────────────────────┘        │
                                                   ▼  the Document
                         env  ──▶ untyped/_parse_env  (casing + types from the Document)
                         argv ──▶ untyped/_parse_cli  (casing + types from the Document)
                                                   │
                     _deep_merge(doc, env) ─▶ _deep_merge(·, cli) ─▶ resolve() ─▶ write
```

This is a second pipeline, deliberately: `_pipeline._merge_sources` must stay the single
implementation for the five *typed* front-ends. What must **not** be duplicated is the
file-layer ordering, so extract it.

---

## Implementation

### Phase 1 — extract the shared file layer (no behavior change)

- Move `_load_cli_config` (`_pipeline.py:44-69`) into `_files.py`. It is pure file loading and
  model-free; it belongs there.
- Extract `_pipeline.py:336-344` (the four-way ordering: `files=`, `env_config`, lexicographically
  sorted `CONFIG__*` pointers, left-to-right CLI `--config`) into
  `_files.order_config_layer(file_entries, env_configs, cli_configs, *, union_tag)`. Have
  `_merge_sources` call it. Both pipelines then share one ordering implementation, honoring the
  invariant above.
- `tests/cli/test_backend_contract.py::TestPipelineParity` and `tests/test_config_files.py` must
  pass unchanged — this phase is a pure move.

### Phase 2 — the Document (`src/confarg/untyped/_document.py`)

Wraps the composed dict and answers what the target used to answer:

- `resolve_path(parts) -> list[str]` — case-insensitive match of each segment against the keys
  actually present at that node, ambiguity an error. Mirrors `_parse_env._env_spelling`
  but reads dict keys instead of declared members. This is what makes
  `DB__MAX_CONNECTIONS` land on `maxConnections` when the file spells it that way — impossible
  today, where a node with no declared members falls back to `part.lower()`.
- `value_at(parts)` / `exists(parts)` — walks dicts by key and lists by integer index, exactly as
  `_pipeline._lookup_declared` (`_pipeline.py:99-117`) does. Reuse that walk rather than rewriting.
- `accepts_container(parts)` — whether a `{`/`[`-leading token should be JSON-decoded, answered
  from the existing value's type. Replaces the type-driven `_parse_env._accepts_json_for`.

### Phase 3 — value inference (`src/confarg/untyped/_infer.py`)

`infer(token, existing, path)`:
1. an explicit cast (`.str/.int/.float/.bool/.json`, via `_cast.FORCE_CAST_NAMES`) wins, and —
   unlike the typed path — resolves **eagerly** rather than storing `_Pinned`, because
   `_serialize_pinned` (`_serialize.py:327`) would otherwise write `{__cast__, __value__}` into
   the output file;
2. key exists in the Document → `typedload._coerce._coerce_leaf(type(existing), token, path)`,
   the same call `_pipeline._coerce_override:144` already makes for locals. Container-for-scalar
   swaps raise, as they do there;
3. key absent (only reachable under `--allow-new`) → YAML-1.1-style scalar resolution:
   `null/~/none` → `None`, `true/false/yes/no/on/off` → bool, int, float, else `str`;
4. `${...}` tokens pass through untouched (`dictexpr.contains_expression`), as
   `_coerce_override:131` already does.

### Phase 4 — model-less env and CLI parsers

`src/confarg/untyped/_parse_env.py` — same spellings as `_parse_env.py`, Document-driven:
prefix strip incl. `removeprefix(separator)` (`_parse_env.py:405-410`), separator split, trailing
`-` delete (`:416`), `__json` cast and root `JSON`, `CONFIG[__SUBPATH]` pointers. **Add the append
spelling the typed path lacks** (`FOO__ITEMS+`), closing FEAT-18 on this channel for free — the
`"+"` sentinel is already understood by `_merge._apply_append_key`.

`src/confarg/untyped/_parse_cli.py` — `--a.b.c V`, `--a.b=V`, `--f+ V…`, `--f.N-`, `--f.key-`,
negative indices, `--f.int V`, root `--json '{…}'`, `--config[.sub][+] FILE`. Arity, which the
typed parser derives from the field type, comes instead from the Document (an existing list takes
greedy tokens; anything else takes one) — with `--f='[1,2]'` as the always-available escape.

Both emit the existing sentinel vocabulary (`+ - * ~ N`, `DICT_DELETE`) so `_merge._deep_merge`
and `_apply_list_ops` apply unchanged, and both raise a new
`exceptions.UnknownKeyError` (modeled on `LocalsError.not_declared`) for a path absent from the
Document unless `--allow-new` is set.

### Phase 5 — composing and writing

`src/confarg/untyped/_compose.py` — `compose(...) -> dict`: the two-phase pipeline above, ending
in `dictexpr.resolve_expressions` (skippable with `--no-resolve`, which keeps `${...}` verbatim —
the seam `01-pipeline-and-contracts.md:46` describes).

`src/confarg/untyped/_write.py`:
- ruamel.yaml / tomlkit when installed — load the *primary* input with the round-trip loader, apply
  the merged result onto that tree key by key, and dump, so comments, key order and quoting
  survive. Lazily imported with `InvalidConfigFileError.missing_library`, matching how
  `_files.py:57` handles PyYAML.
- fallback to `_files._dump_file(_serialize._serialize_untyped(data), path)` — today's behavior.
- atomic write (temp file + replace), `--backup`, `--dry-run`, `--diff` (unified diff via
  `difflib`), `--check` (exit 1 if the file would change), `--format` for conversion.

### Phase 6 — the console script

`[project.scripts] confarg = "confarg.__main__:main"`, subcommand `merge`, argparse-only so the
zero-dependency stance (`docs-dev/architecture/design-decisions/README.md:126`) holds.

**Flag-collision resolution** — the exact problem FEAT-10 flags: a user path could be named
`--output`. Tool options go before a `--` separator, overrides after it:

```
confarg merge base.yaml prod.yaml -o out.yaml --diff -- --db.port 5433 --tags+ a b --old.key-
```

The outer argparse consumes `--`, so the override vector is unambiguous and confarg's own lack of
an end-of-options separator (FEAT-17) never bites.

New extra: `roundtrip = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]`.

---

## Files

| Path | Change |
|---|---|
| `src/confarg/_files.py` | +`order_config_layer`, +`_load_cli_config` (moved in) |
| `src/confarg/_pipeline.py` | call `order_config_layer`; drop the moved function |
| `src/confarg/untyped/{__init__,_document,_infer,_parse_env,_parse_cli,_compose,_write}.py` | new |
| `src/confarg/__main__.py`, `src/confarg/_cli_app.py` | new console script |
| `src/confarg/exceptions.py` | +`UnknownKeyError` |
| `pyproject.toml` | +`[project.scripts]`, +`roundtrip` extra |
| `tests/untyped/` | new suite |
| `examples/101_rewrite/` + `docs/examples/101_rewrite/README.md` | new tutorial |
| `docs-dev/architecture/untyped-rewriting.md` | new topic; cross-link from `pipeline/` and `limitations.md` |

Reused as-is, not reimplemented: `_files` (formats, `__include__`, mounting, dumpers), `_merge`
(the whole patch vocabulary), `dictexpr` (expressions and anchoring), `_cast`, `_defaults`,
`exceptions`, `typedload._coerce._coerce_leaf`, `_serialize._serialize_untyped`, and
`_pipeline._lookup_declared`/`_lookup_path` as the Document walk.

---

## Verification

1. `uv run pytest` — Phase 1 is a pure move, so the existing ~2,093 tests must pass untouched,
   `TestPipelineParity` in particular.
2. New `tests/untyped/`, reusing `tests/conftest.py`'s `tmp_yaml`/`tmp_toml`/`tmp_json` writers
   (`conftest.py:509-554`):
   - **Composition parity** — for a document whose values already have the right types,
     `compose(files=…, argv=…, env=…)` must equal `dump_file(merge(Target, …))`. This pins that
     the untyped path never diverges from confarg's composition semantics: includes, list
     layering, cycle detection, subpath mounting, the `+ - * ~ N` sentinels, expression anchoring.
   - **Idempotence** — `compose(compose(x))` byte-equals `compose(x)`. The typed path deliberately
     does not guarantee this (`01-pipeline-and-contracts.md:59`); for a rewriter it is the point.
   - **Round-trip fidelity** — comments, key order and quoting preserved with the extra installed;
     clean degradation with a clear message without it.
   - **Strictness** — `--db.prot 5433` raises `UnknownKeyError` naming the path; `--allow-new`
     creates it.
   - **Inference** — `PORT=8080` over `port: 80` yields int `8080`; over `port: "80"` yields
     `"8080"`; `--port.int 8080` yields `8080` as a bare scalar, never `{__cast__: …}`.
   - Hypothesis test over `valid_identifiers` / `leaf_*` (`conftest.py:615-627`) for
     set → write → read → same value.
3. `examples/101_rewrite/README.md` console blocks execute as subprocess tests under
   `pytest-markdown-console`, the same way the other 24 examples do.
4. Manual end-to-end:
   `uv run confarg merge examples/configs/<a>.yaml -o out.yaml --diff -- --db.port 5433 --tags+ x`
   then re-run with `--check` and confirm exit 0 (idempotent), and `--format toml -o out.toml`.

---

## Open question

Packaging is the one decision not settled by the user: this plan assumes **inside the confarg
distribution**. Switching to a separate package or to an extracted `confarg-core` changes Phase 1
and the `Files` table, but none of Phases 2–6.

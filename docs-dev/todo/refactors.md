# Refactors

Code that works but should be cleaner: duplication, misplaced modules, dead weight, test
hygiene, performance. See [README.md](README.md) for the ticket format.

## Structure

### REF-2 — The scalar-cast table exists three times

**Where:** `_cast.SCALAR_CAST_TYPES`, `typedload/_construct._CAST_TYPE_NAMES`,
`cli/argparse/_build._SCALAR_CAST_TYPES` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** medium

Three copies of the same list of castable scalar types, one per call site. `_cast` should own
it and the other two should import it — a new cast type currently has to be added in three
places to work everywhere. See [09-invariants.md](../architecture/09-invariants.md).

`_cast` now also derives the reverse map, `cast_name_for_type`, which names a `_Pinned` on the
way out; `_construct._CAST_TYPE_NAMES` is the copy that reads that name back, so folding it in
is what keeps the writer and the reader on one table.

### REF-3 — `_add_*` wrappers survive only for completion

**Where:** `src/confarg/cli/argparse/_register.py` · **Filed:** 2026-09-12
**Effort:** M · **Risk:** medium

The thin `_add_*` helpers exist because `_completion.py` needs the `argparse` action objects.
Refactoring completion onto `FlagSpec` would delete them.

### REF-4 — `tests/examples/_registry.py` is orphaned

**Where:** `tests/examples/_registry.py` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** low

It describes a README replay harness (`test_readme_commands.py`) that no longer exists; README
commands are now replayed by `pytest-markdown-console`. Delete it or re-point it.
See [12-testing.md](../architecture/12-testing.md).

### REF-15 — `examples/17_removing_items/myapp.py` imports a module that does not exist

**Where:** `examples/17_removing_items/myapp.py` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

`from configs.deletion import Config` — `examples/configs/src/configs/` has no `deletion.py`,
so the script dies with `ModuleNotFoundError` on import. Nothing catches it: the example's
`README.md` never invokes `myapp.py`, so `pytest-markdown-console` does not replay it, and the
only signal is a `ty check` `unresolved-import`. Point it at a real config module or delete it.

## Duplication

### REF-17 — `_var_param_names` / `_var_positional_name` / `_var_keyword_name` re-inspect the same signature

**Where:** `src/confarg/_types.py` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

Three helpers each independently call `inspect.signature(tp.__init__)` and walk parameters for
`VAR_POSITIONAL` / `VAR_KEYWORD` (`_var_param_names`, `_var_positional_name`, `_var_keyword_name`).
`_construct.py` calls two of them back-to-back at lines 368-369. Replace with a single
`_var_params(tp) -> _VarParams(pos_name, kw_name)` (both `None` for dataclasses) that inspects once;
`_construct.py` then reads `vp = _var_params(tp)`. Removes ~25 lines and one redundant inspection
per struct construction.

### REF-18 — `_resolve_single` duplicates its exception-handling chain

**Where:** `src/confarg/dictexpr/_expressions.py` (`_resolve_single`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

The pure-expression branch (lines 553-562) and the interpolation branch (lines 577-587) each repeat
the same try/except shape: re-raise `MissingReferenceError` / `UnsafeExpressionError` /
`ExpressionEvalError`, then wrap any other `Exception` in `ExpressionEvalError` with a context
message. The two re-raise clauses are load-bearing (they stop the catch-all from swallowing the
typed errors) but collapse to one tuple: `except (MissingReferenceError, UnsafeExpressionError,
ExpressionEvalError): raise`. Better: extract `_eval_expr(tree, namespace, context)` so the
evaluate-and-handle logic lives once and both paths call it. ~20 lines.

### REF-19 — YAML/JSON dict loaders duplicate their item-loader counterparts

**Where:** `src/confarg/_files.py` (`_load_yaml`/`_load_yaml_item`, `_load_json`/`_load_json_item`)
· **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

Each pair duplicates the optional-import guard, the `FileNotFoundError` → `not_found` mapping, and
the parse-error → `malformed` mapping; the only difference is that the dict variant enforces
`isinstance(data, dict)`. Extract `_read_yaml_raw(path)` / `_read_json_raw(path)` returning the raw
top-level value; the dict wrappers become one-liners (`data = _read_yaml_raw(path); return data if
isinstance(data, dict) else {}`). Removes ~30 lines of repeated error mapping.

### REF-21 — `_construct_sequence` / `_construct_list` / `_construct_set` are three thin wrappers

**Where:** `src/confarg/typedload/_construct.py` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

`_construct_sequence` (line 189) just dispatches `_is_list` → `_construct_list`, else
`_construct_set`; both leaf functions are thin wrappers over `_build_items` — one returns the list,
the other `set(...)` / `frozenset(...)`. Fold all three into one `_construct_collection(tp, data,
path, union_tag)` that calls `_build_items` and wraps the result with the right constructor from
`_origin(tp)`. Removes two one-line functions and the dispatch indirection.

### REF-22 — `_store_env_value` buries a JSON-autodetect predicate in nested `any(...)` calls

**Where:** `src/confarg/_parse_env.py` (`_store_env_value`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

`_store_env_value` (lines 289-326) builds two large boolean expressions `accepts_obj` / `accepts_arr`
with triple-nested `any(... for v in _union_args_no_none(ft))` checks to decide whether a `[`/`{`-led
env value should be parsed as JSON. Extract `_accepts_json_for(ft, value) -> bool` (returns True
when `ft` is a struct/namedtuple/dict/callable/union-with-such and the value's opening bracket
matches); the body then reads as a clean three-step: try JSON autodetect, else `_try_coerce`.
Reduces nesting and ~10 lines.

### REF-23 — `_build_leaf_spec` repeats `group` / `group_description` on every FlagSpec

**Where:** `src/confarg/cli/_build.py` (`_build_leaf_spec`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

Seven `FlagSpec(...)` constructors in `_build_leaf_spec` (lines 117-207) each repeat
`group=group, group_description=group_description`. Build the common kwargs once (`common = dict(group=
group, group_description=group_description, help=help_text)`) and splat it, so each branch specifies
only what differs (`name`, `metavar`, `nargs`, `choices`). Removes ~14 repeated kwarg lines.

### REF-24 — Minor cleanups in `_parse_cli` and `_coerce`

**Where:** `src/confarg/_parse_cli.py`, `src/confarg/typedload/_coerce.py` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

Grab-bag of small, low-risk tidyings found while analyzing the two modules:

1. `_looks_like_flag` (lines 360-365) uses a `_double_dash = "--"` local plus `len(_double_dash)`
   indexing; clearer as a `len(token) > 2 and (token[2].isalpha() or token[2] == "_")` one-liner.
2. `_coerce_leaf` (line 251) and `_try_coerce` (line 291) keep parallel "is this coercible" predicates
   (`_is_literal or _is_enum or ft in (bool, int, float) or ft in _LEAF_COERCIONS or _is_none_type`).
   A single `_is_eagerly_coercible(tp)` predicate would keep them aligned. Lower priority — the two
   diverge intentionally on raise-vs-return, so share only the predicate, not the behavior.

## Robustness

### REF-5 — `_import_dotted` conflates two failures

**Where:** `src/confarg/_import.py` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** medium

It assumes no builtin name collides with an importable module, and treats an `ImportError`
raised _inside_ a module the same as "this is not a module" — so a broken dependency reads as
a typo'd path. See [05-types-and-construction.md#dotted-imports](../architecture/05-types-and-construction.md#dotted-imports).

### REF-6 — `LIST_APPEND_KEY` accepts a value nothing produces

**Where:** `src/confarg/_merge.py` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** high

The index-keyed dict branch was added "for future env-var support" that never arrived. Either
wire up the env path or drop the branch; untested speculative code in the merge core is worse
than neither.

## Performance

### REF-7 — Expression resolution repeats work

**Where:** `src/confarg/dictexpr/_expressions.py` · **Filed:** 2026-09-12
**Effort:** M · **Risk:** medium

The topological sort is quadratic in the number of expressions, and each expression is parsed
several times (dependency extraction, safety check, evaluation). Parse once into a cached AST
keyed by the expression text. Only matters for large configurations — measure before
rewriting. See [07-expressions.md](../architecture/07-expressions.md).

## Test hygiene

### REF-8 — Tests use `env_prefix=""`

**Where:** `tests/` (~160 call sites) · **Filed:** 2026-09-12
**Effort:** M · **Risk:** low

An empty prefix means every environment variable in the process is a candidate field, which is
neither what users do nor what the default (`None`, off) encourages. Use a realistic prefix
such as `MYAPP_`, and keep `""` only where the empty prefix is the behavior under test.
See [10-design-decisions.md#environment-variables-off-by-default](../architecture/10-design-decisions.md#environment-variables-off-by-default).

### REF-14 — A dynamic-flag test passes for the wrong reason

**Where:** `tests/cli/argparse/test_gaps.py` (`test_build_dynamic_flags_exception_returns_empty`)
· **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

The test claims to exercise the error handler in `build_dynamic_flags` by passing `None` as
the target, but `None` raises nothing: the scan simply finds no flags and returns `[]`.
Verified while closing BUG-5 — with the handler now warning, that call emits no warning, so
the handler is never reached. The monkeypatch test next to it
(`test_build_dynamic_flags_warns_on_internal_error`) already covers the real path, so this
one is either deleted or rewritten around an input that genuinely fails.

### REF-26 — Tests of the neutral flag model still live under `tests/cli/argparse/`

**Where:** `tests/cli/argparse/test_gaps.py`, `test_final.py` · **Filed:** 2026-09-15
**Effort:** M · **Risk:** low

REF-1 moved `_spec.py` and `_build.py` to `cli/`, but their tests stayed where they were, so
`tests/` no longer mirrors `src/confarg/`. `test_gaps.py` mixes specs-and-build tests with
genuinely argparse-specific `_register` / `_completion` ones; `test_final.py` is a topic file
(Final support across coercion, build and completion) that resists a clean split. Extract the
neutral halves into `tests/cli/test_build.py` / `test_spec.py`, or decide the topic layout wins
over the mirror rule and say so in [12-testing.md](../architecture/12-testing.md).

## Sweeps

### REF-9 — Review public argument names and order

**Where:** `src/confarg/_api.py`, `src/confarg/cli/*/` · **Filed:** 2026-09-12
**Effort:** L · **Risk:** medium

The keyword sets of `load` / `merge` / `build` and the three adapter triads grew one feature at
a time. Review names and ordering once, while the library is not shipping and breaking changes
are free. See [01-pipeline-and-contracts.md#public-api-seams](../architecture/01-pipeline-and-contracts.md#public-api-seams).

### REF-10 — Sweep for code obsoleted by past refactors

**Where:** `src/confarg/` · **Filed:** 2026-09-12
**Effort:** M · **Risk:** high

Helpers, branches and parameters kept alive by a single caller that a later refactor made
redundant. Worth one deliberate pass with coverage data rather than opportunistic deletions.

### REF-26 — The `--config` files named on argv are parsed three times per run

**Where:** `src/confarg/_tags.py` (`_partial_config_from_argv`), `src/confarg/cli/_build.py`,
`src/confarg/_pipeline.py` · **Filed:** 2026-09-15
**Effort:** M · **Risk:** low

`_partial_config_from_argv` re-reads and re-parses every file argv names, and three callers now
want the same answer independently: `build_static_flags` (to import tagged classes),
`build_dynamic_flags` (to find callable openers), and `_parse_cli` (to import tagged classes
again), before the pipeline reads the files a fourth time for their actual contents. Nothing is
wrong with the result — the reads are idempotent and only happen when `--config` is present —
but the same bytes are parsed once per caller. A small argv-keyed cache, or threading one
pre-parsed dict through the registration path, would collapse them. Grew from one caller to
three when BUG-6 closed.

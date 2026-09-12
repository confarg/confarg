# Refactors

Code that works but should be cleaner: duplication, misplaced modules, dead weight, test
hygiene, performance. See [README.md](README.md) for the ticket format.

## Structure

### REF-1 — The framework-neutral flag model lives under `cli/argparse/`

**Where:** `src/confarg/cli/argparse/_spec.py`, `_build.py` · **Filed:** 2026-09-12

`FlagSpec`, `FieldMeta` and the spec generation in `_build.py` are used by every adapter, not
just argparse; they sit under `cli/argparse/` by historical accident and belong in `cli/`.
Confirmed by the maintainer as an accident, not a decision.
See [04-cli-adapters.md#framework-neutral-flag-model](../architecture/04-cli-adapters.md#framework-neutral-flag-model).

### REF-2 — The scalar-cast table exists three times

**Where:** `_cast.SCALAR_CAST_TYPES`, `typedload/_construct._CAST_TYPE_NAMES`,
`cli/argparse/_build._SCALAR_CAST_TYPES` · **Filed:** 2026-09-12

Three copies of the same list of castable scalar types, one per call site. `_cast` should own
it and the other two should import it — a new cast type currently has to be added in three
places to work everywhere. See [09-invariants.md](../architecture/09-invariants.md).

### REF-3 — `_add_*` wrappers survive only for completion

**Where:** `src/confarg/cli/argparse/_register.py` · **Filed:** 2026-09-12

The thin `_add_*` helpers exist because `_completion.py` needs the `argparse` action objects.
Refactoring completion onto `FlagSpec` would delete them.

### REF-4 — `tests/examples/_registry.py` is orphaned

**Where:** `tests/examples/_registry.py` · **Filed:** 2026-09-12

It describes a README replay harness (`test_readme_commands.py`) that no longer exists; README
commands are now replayed by `pytest-markdown-console`. Delete it or re-point it.
See [12-testing.md](../architecture/12-testing.md).

## Robustness

### REF-5 — `_import_dotted` conflates two failures

**Where:** `src/confarg/_import.py` · **Filed:** 2026-09-12

It assumes no builtin name collides with an importable module, and treats an `ImportError`
raised *inside* a module the same as "this is not a module" — so a broken dependency reads as
a typo'd path. See [05-types-and-construction.md#dotted-imports](../architecture/05-types-and-construction.md#dotted-imports).

### REF-6 — `LIST_APPEND_KEY` accepts a value nothing produces

**Where:** `src/confarg/_merge.py` · **Filed:** 2026-09-12

The index-keyed dict branch was added "for future env-var support" that never arrived. Either
wire up the env path or drop the branch; untested speculative code in the merge core is worse
than neither.

## Performance

### REF-7 — Expression resolution repeats work

**Where:** `src/confarg/dictexpr/_expressions.py` · **Filed:** 2026-09-12

The topological sort is quadratic in the number of expressions, and each expression is parsed
several times (dependency extraction, safety check, evaluation). Parse once into a cached AST
keyed by the expression text. Only matters for large configurations — measure before
rewriting. See [07-expressions.md](../architecture/07-expressions.md).

## Test hygiene

### REF-8 — Tests use `env_prefix=""`

**Where:** `tests/` (~160 call sites) · **Filed:** 2026-09-12

An empty prefix means every environment variable in the process is a candidate field, which is
neither what users do nor what the default (`None`, off) encourages. Use a realistic prefix
such as `MYAPP_`, and keep `""` only where the empty prefix is the behavior under test.
See [10-design-decisions.md#environment-variables-off-by-default](../architecture/10-design-decisions.md#environment-variables-off-by-default).

### REF-11 — A test run leaves artifacts in the working copy

**Where:** `examples/21_expressions/` · **Filed:** 2026-09-12

A full `uv run pytest` writes `saved_config_interpolated.yaml` and
`saved_config_uninterpolated.yaml` next to the example, so every run dirties the working copy
with untracked files that have to be deleted by hand before describing a revision. The README
command that produces them should write to a temporary directory, or the paths should be
ignored.

## Sweeps

### REF-9 — Review public argument names and order

**Where:** `src/confarg/_api.py`, `src/confarg/cli/*/` · **Filed:** 2026-09-12

The keyword sets of `load` / `merge` / `build` and the three adapter triads grew one feature at
a time. Review names and ordering once, while the library is not shipping and breaking changes
are free. See [01-pipeline-and-contracts.md#public-api-seams](../architecture/01-pipeline-and-contracts.md#public-api-seams).

### REF-10 — Sweep for code obsoleted by past refactors

**Where:** `src/confarg/` · **Filed:** 2026-09-12

Helpers, branches and parameters kept alive by a single caller that a later refactor made
redundant. Worth one deliberate pass with coverage data rather than opportunistic deletions.

# Refactors

Code that works but should be cleaner: duplication, misplaced modules, dead weight, test
hygiene, performance. See [README.md](README.md) for the ticket format.

## Structure

### REF-1 — The framework-neutral flag model lives under `cli/argparse/`

**Where:** `src/confarg/cli/argparse/_spec.py`, `_build.py` · **Filed:** 2026-09-12
**Effort:** M · **Risk:** low

`FlagSpec`, `FieldMeta` and the spec generation in `_build.py` are used by every adapter, not
just argparse; they sit under `cli/argparse/` by historical accident and belong in `cli/`.
Confirmed by the maintainer as an accident, not a decision.
See [04-cli-adapters.md#framework-neutral-flag-model](../architecture/04-cli-adapters.md#framework-neutral-flag-model).

### REF-2 — The scalar-cast table exists three times

**Where:** `_cast.SCALAR_CAST_TYPES`, `typedload/_construct._CAST_TYPE_NAMES`,
`cli/argparse/_build._SCALAR_CAST_TYPES` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** medium

Three copies of the same list of castable scalar types, one per call site. `_cast` should own
it and the other two should import it — a new cast type currently has to be added in three
places to work everywhere. See [09-invariants.md](../architecture/09-invariants.md).

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

### REF-13 — `AGENTS.md` has drifted from `CLAUDE.md`

**Where:** `AGENTS.md` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

The two files are meant to tell different agents the same thing, but `AGENTS.md` stopped at an
older revision: it still lists the public API function by function and lacks the architecture,
boards, testing and contributing sections entirely, so a non-Claude agent never learns about
`docs-dev/`, the drive-by ticket rule or the parity mandate. Decide whether one file is
generated from the other or is a symlink to it; two hand-maintained copies are what produced
the drift. Both are `.gitignore`d (`.gitignore:226-227`), so no CI check can catch it.

## Robustness

### REF-5 — `_import_dotted` conflates two failures

**Where:** `src/confarg/_import.py` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** medium

It assumes no builtin name collides with an importable module, and treats an `ImportError`
raised *inside* a module the same as "this is not a module" — so a broken dependency reads as
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

### REF-11 — A test run leaves artifacts in the working copy

**Where:** `examples/21_expressions/` · **Filed:** 2026-09-12
**Effort:** S · **Risk:** low

A full `uv run pytest` writes `saved_config_interpolated.yaml` and
`saved_config_uninterpolated.yaml` next to the example, so every run dirties the working copy
with untracked files that have to be deleted by hand before describing a revision. The README
command that produces them should write to a temporary directory, or the paths should be
ignored.

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

# REF-10 — Sweep for code obsoleted by past refactors

**Where:** `src/confarg/` · **Filed:** 2026-09-12
**Effort:** M · **Risk:** high · **Impact:** none

Helpers, branches and parameters kept alive by a single caller that a later refactor made
redundant. Worth one deliberate pass with coverage data rather than opportunistic deletions.

**"One caller" turned out not to be the signal.** 202 of the 390 private functions in `src/` are
referenced once, and sampling them — `_construct_namedtuple`, `_specs_for_field`,
`_resolve_fn_spec` — shows deliberate decomposition of long functions and dispatch-table entries,
not dead weight. Inlining them would make the code worse. Score candidates by reachability
instead, which is what the audit of 2026-09-24 did; what it verified is already filed:

- zero-caller helpers and unreachable evaluator branches, in
  [REF-52](REF-52-mechanical-collapses-in-the-type-machinery.md);
- an ignored parameter, a test-only code path and an unused assignment in the argparse adapter, in
  [REF-42](REF-42-argparse-completion-reimplements-the-build-walk.md) and
  [REF-50](REF-50-adapter-registration-boilerplate.md).

What is left for this ticket is the part that needs coverage data rather than reading: branches
reachable in principle but exercised by no test and no documented behavior. Note the pattern
REF-52 names — a coverage test that calls a private function directly, bypassing the validation
that makes the branch unreachable, keeps that branch alive and hides it from exactly this sweep.

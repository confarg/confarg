---
filed: 2026-10-20
where:
  - src/confarg/cli/_sources.py::reconcile
  - src/confarg/cli/argparse/_namespace.py
  - src/confarg/cli/_clicklike/_context.py
  - src/confarg/cli/cyclopts/_context.py
effort: S
risk: low
impact: none
severity: trivial
---

# REF-114 — Each adapter reconciles its registration by hand

`cli/_sources` records what `populate_*` read as a `Registration`, and every merge step reads it back the same two ways, spelled per adapter:

- the options: argparse's `_options`, clicklike's `ctx_options` and cyclopts' `_app_options` are each `_resolve_options(caller, reconcile(<registration>, opts, caller))`, differing only in how they find the registration;
- the runs: `runs=None if registration is None else registration.runs` at argparse's `_merge_namespace` and cyclopts' `_merge_app`, `found.runs` at clicklike's `merge_from_ctx`.

Fix direction: `_sources` offers `options_for(registration, caller, opts)` and `runs_of(registration)`, so each adapter keeps only its lookup (`_registration`, `registration`, `_app_registration`), as [cli-prefix-at-registration.md](../../architecture/design-decisions/cli-prefix-at-registration.md#cli_prefix-is-given-at-registration-and-recovered-at-merge) already has `resolve_prefix` serve every adapter for the prefix.

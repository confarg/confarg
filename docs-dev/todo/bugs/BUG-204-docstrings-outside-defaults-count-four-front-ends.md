---
filed: 2026-10-07
where:
  - src/confarg/cli/_build.py::_collect_callable_key_argv_specs  # its docstring
  - tests/cli/test_backend_contract.py::TestLocalsContract  # the class docstring and the nested-local test's
  - tests/cli/test_backend_contract.py::TestDashPrefixedValueContract  # its class docstring
  - docs-dev/todo/features/FEAT-12-scoped-expression-expansion.md  # its parity paragraph
effort: S
risk: low
impact: none
severity: trivial
introduced_by: [BUG-7]  # PR-194, which added typer and updated the counts in docs-dev/ only
---
# BUG-204 — Docstrings outside `_defaults.py` and an open ticket count four front-ends

Four more sites say "four front-ends" where the architecture counts five — vanilla, argparse,
click, typer, cyclopts
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)). BUG-119
covers the two in `_defaults.py`; these are the same sweep miss elsewhere. Three of them sit in
docstrings of tests that run against the five-way `loader` fixture, so they understate their own
coverage. Fix direction: say five, or drop the count, as BUG-119 proposes.

Origin: latent-stale from BUG-7, which added the typer front-end (PR-194) and changed "four" to
"five" across `docs-dev/architecture/` only. Every site was right when written — `_build.py`'s
docstring by the BUG-28/29 fix (PR-169, 2026-09-17), the two `TestLocalsContract` docstrings by
PR-105, `TestDashPrefixedValueContract`'s by the BUG-27 fix (PR-170), and FEAT-12 was filed
2026-09-12 — all before the typer merge. BUG-119 and BUG-150 share this origin.

```console
$ grep -rn "four front-ends" src/ tests/ docs-dev/todo/features/ | grep -v __pycache__
src/confarg/cli/_build.py:1303:    in all four front-ends.
src/confarg/_defaults.py:7:Always reference these constants instead of repeating the literals, so the four front-ends
src/confarg/_defaults.py:64:Every channel writes it and ``build`` reads it, so all four front-ends have to agree on the
tests/cli/test_backend_contract.py:6211:    variable.  These tests pin all of that across the four front-ends.
tests/cli/test_backend_contract.py:6376:        """The declared-ness check follows the namespace down, in all four front-ends."""
tests/cli/test_backend_contract.py:6690:    shared argv scan, so they were broken in all four front-ends.
docs-dev/todo/features/FEAT-12-scoped-expression-expansion.md:41:Parity is not at risk — the engine is shared by all three channels and all four front-ends, so
# expected: only the _defaults.py lines, which BUG-119 already covers
# actual:   six sites count four front-ends; there are five
```

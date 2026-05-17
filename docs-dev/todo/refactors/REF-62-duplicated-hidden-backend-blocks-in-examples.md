# REF-62 — Hidden backend blocks are replayed twice per section in the example READMEs

**Where:** `examples/2_input_precedence/README.md` (typical; also `1_three_input_sources`,
`21_expressions`, `22_variable_scopes` and others) · **Filed:** 2026-09-27 ·
*(inferred — no run was profiled, the duplication is visible in the text)*
**Effort:** S · **Risk:** low · **Impact:** none

Most sections show one visible `myapp.py` block, then hidden backend blocks for argparse,
click, cyclopts and typer — and then a second, identical set of hidden click, cyclopts and
typer blocks. Every replayed block is a subprocess under `pytest-markdown-console`, so the
duplicate set doubles part of an already slow test run without adding coverage. Either the
duplicates are leftovers from an edit and should go, or they are deliberate (e.g. ordering
experiments) and deserve a comment saying so — but they sit inside the blocks the snippet
hook owns, so the fix must keep the hook in mind.

---
filed: 2026-09-24
where:
  - src/confarg/cli/click/_context.py
  - src/confarg/cli/typer/_context.py
  - src/confarg/cli/click/_completion.py
  - src/confarg/cli/typer/_completion.py
effort: S
risk: low
impact: none
severity: trivial
needs_design: true  # the choice below is the maintainer's; the work after it is a few lines either way
---

# REF-41 — Keep the click and typer docstrings literal, or assign them from a template

What the two pairs, `cli/{click,typer}/_context.py` and `cli/{click,typer}/_completion.py`, still duplicate is docstring prose only.
Every body is a one-line forward to the shared layer (`_clicklike.merge_from_ctx`, `construct_from_ctx`, `setup_completion`), and the one difference in *code* is the annotation (`click.Context` against `typer.Context`, `click.Command` against `typer._click.Command`), which stays per framework so the narrowing type is not lost.
The invariant that "anything both adapters need lives in `cli/_clicklike/`" ([invariants.md#fragile-couplings](../../architecture/invariants.md#fragile-couplings)) is met by the code; the question is whether it extends to the prose, which differs by a framework's name (`click.get_current_context` against "declare it as a parameter", "Click" against "Typer", `command.main()` against "invoking the command").

Sharing the prose means assigning `__doc__` at runtime from a template, in each of the four modules.
What that costs:

- IDE hover and static documentation readers (griffe) see no docstring, since neither runs the assignment.
- ruff `D103` fires on every such function (run: `Missing docstring in public function` on a `def` whose `__doc__` is assigned below it), so each needs a `# noqa: D103  # reason`.

What it leaves alone: `help()`, `tests/cli/test_public_docstrings.py` (it reads `inspect.getdoc`, which sees the assigned text), and the published site, which renders `::: confarg` only (`docs/reference.md`), so neither module's docstrings reach it either way.

Options:

- **(a) Runtime templates.**
  The prose written once per pair, assigned with the framework's names filled in; the costs above, for about 100 lines of docstrings saved.
- **(b) Keep the literal docstrings**, and close the ticket with a `Rejected:` paragraph in [clicklike-seam.md](../../architecture/cli-adapters/clicklike-seam.md#the-clicklike-seam) saying the prose is the part each framework's reader sees, and that a template would trade it for the costs above.

Precedent: pandas' `@doc` decorator fills a shared template into docstrings at import time, at the same costs (read in its source, not run here).

Recommendation: (b).

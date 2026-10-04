# REF-41 — `cli/click/_context.py` and `cli/typer/_context.py` are the same file

**Where:** `src/confarg/cli/click/_context.py`, `src/confarg/cli/typer/_context.py` ·
**Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

71 lines each; `diff` reports 18 differing lines, and the only difference in *code* is the
annotation `ctx: click.Context` versus `ctx: typer.Context`. Both bodies are a one-line forward
to `_clicklike.merge_from_ctx` / `construct_from_ctx` with the options resolved; everything else
that differs is docstring wording.

This is a documented invariant being broken
([invariants.md#fragile-couplings](../../architecture/invariants.md#fragile-couplings)):
*"Anything the click and typer adapters both need lives in `cli/_clicklike/`, parameterised by
the classes the two frameworks spell differently — never duplicated into both packages."*
Roughly 70 lines exist to carry two type annotations.

Fix direction: **keep** the per-framework annotation rather than re-exporting the shared function
under the public name, so the narrowing `ctx:` type is not lost. What is left to share is the
docstring prose of the two pairs.

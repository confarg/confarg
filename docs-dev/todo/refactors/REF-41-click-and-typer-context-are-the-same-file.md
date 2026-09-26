# REF-41 — `cli/click/_context.py` and `cli/typer/_context.py` are the same file

**Where:** `src/confarg/cli/click/_context.py`, `src/confarg/cli/typer/_context.py` ·
**Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

160 and 158 lines; `diff` reports 24 differing lines, and the only difference in *code* is the
annotation `ctx: click.Context` versus `ctx: typer.Context`. Both bodies are a verbatim
twelve-line keyword forward to `_clicklike.merge_from_ctx` / `construct_from_ctx`, which already
carry the identical signature. Everything else that differs is docstring wording.

This is a documented invariant being broken
([09-invariants.md#fragile-couplings](../../architecture/09-invariants.md#fragile-couplings)):
*"Anything the click and typer adapters both need lives in `cli/_clicklike/`, parameterised by
the classes the two frameworks spell differently — never duplicated into both packages."*
Roughly 150 lines exist to carry two type annotations.

Fix direction: **keep** the per-framework annotation rather than re-exporting the shared function
under the public name, so the narrowing `ctx:` type is not lost. Combined with
[REF-40](REF-40-option-surface-spelled-fourteen-times.md) each public function becomes three
lines — the signature, a one-line docstring pointing at `confarg.merge`, and the forward.

Also in scope, same shape: all four `from_*` are mechanically `merge_*(...)` followed by
`_construct_from_merged(target, merged, union_tag)`, which is twelve to fourteen lines of pure
keyword relay each.

# REF-7 — Expression resolution repeats work

**Where:** `src/confarg/dictexpr/_expressions.py` · **Filed:** 2026-09-12
**Effort:** M · **Risk:** medium · **Impact:** none

The topological sort is quadratic in the number of expressions, and each expression is parsed
several times (dependency extraction, safety check, evaluation). Parse once into a cached AST
keyed by the expression text. Only matters for large configurations — measure before
rewriting. See [07-expressions.md](../../architecture/07-expressions.md).

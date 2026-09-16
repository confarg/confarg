# REF-18 — `_resolve_single` duplicates its exception-handling chain

**Where:** `src/confarg/dictexpr/_expressions.py` (`_resolve_single`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** none

The pure-expression branch (lines 553-562) and the interpolation branch (lines 577-587) each repeat
the same try/except shape: re-raise `MissingReferenceError` / `UnsafeExpressionError` /
`ExpressionEvalError`, then wrap any other `Exception` in `ExpressionEvalError` with a context
message. The two re-raise clauses are load-bearing (they stop the catch-all from swallowing the
typed errors) but collapse to one tuple: `except (MissingReferenceError, UnsafeExpressionError,
ExpressionEvalError): raise`. Better: extract `_eval_expr(tree, namespace, context)` so the
evaluate-and-handle logic lives once and both paths call it. ~20 lines.

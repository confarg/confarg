# BUG-33 — REF-18 ticket on the refactor board describes work already done

**Where:** `docs-dev/todo/refactors/REF-18-resolve-single-duplicate-exception-chain.md` · **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

REF-18 asked to extract `_eval_expr(tree, namespace, context)` so the evaluate-and-handle
logic lives once and both the pure-expression and interpolation paths call it. That is done:
#156 extracted `_eval_expr` (`dictexpr/_expressions.py:557`) and both paths call it (lines 590
and 607). #156 deleted the ticket from the old single-file `refactors.md`, but the #162 board
split resurrected it as a separate file, so it reads as open work. The same split resurrected
REF-17 (closed by #147) and REF-2 (closed by #144, re-closed by the stack); REF-17 was swept
in the same revision as this ticket. Sweep REF-18 the same way: delete the file and regenerate
the board.

```
$ grep -n "_eval_expr" src/confarg/dictexpr/_expressions.py
557:def _eval_expr(tree: ast.Expression, namespace: dict[str, Any], context: str) -> Any:
590:        return _eval_expr(tree, namespace, expr_str)
607:            value = _eval_expr(tree, namespace, m.group(0))
$ ls docs-dev/todo/refactors/REF-18-resolve-single-duplicate-exception-chain.md
docs-dev/todo/refactors/REF-18-resolve-single-duplicate-exception-chain.md
# expected: ticket deleted — the work it describes is done (#156)
# actual:   ticket still on the board, claiming open work
```

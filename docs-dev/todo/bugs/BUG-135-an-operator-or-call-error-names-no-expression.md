# BUG-135 — An operator or a call that fails names no expression

**Where:** `src/confarg/dictexpr/_expressions.py` (`_eval_binop`, `_eval_call`, `_eval_expr`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** high · **Impact:** behavior

`_eval_expr`'s docstring says a failure raised while evaluating, "typically raised by a
whitelisted function the expression called", becomes an `ExpressionEvalError` that quotes the
expression. That is not what happens for a function or an operator. `_eval_call` and `_eval_binop`
already wrap the failure in an `ExpressionEvalError` with no context, and `_eval_expr` lets that
through unchanged. So `${b / 0}` and `${s.strip(1)}` report Python's bare text, with nothing to
say which expression of the configuration failed, while `${-s}` (unary operator) and `${s < 1}`
(comparison), which `_eval_expr` wraps, name it. Fix direction: one wrapper adds the quoted
context. Either the two evaluators let the plain exception propagate to `_eval_expr`, or
`_eval_expr` words an `ExpressionEvalError` that has none, as
[messages-live-on-exceptions.md](../../architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)
would have it.

```python
from confarg.dictexpr import resolve_expressions

for v in ("${b / 0}", "${s.strip(1)}", "${-s}"):
    try:
        resolve_expressions({"b": 1, "s": "x", "v": v})
    except Exception as exc:
        print(f"{v}: {type(exc).__name__}: {exc}")
# expected: each one quotes its expression, as ${-s} does
# actual:
# ${b / 0}: ExpressionEvalError: division by zero
# ${s.strip(1)}: ExpressionEvalError: strip arg must be None or str
# ${-s}: ExpressionEvalError: Error in expression '${-s}': bad operand type for unary -: 'str'
```

# BUG-143 — An unsafe-expression refusal names no expression

**Where:** `src/confarg/dictexpr/_expressions.py` (`_validate_ast`, `_validate_call`,
`_eval_method`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** high · **Impact:** behavior

A body that does not parse is refused with its text quoted (`Invalid expression syntax:
's.upper('`), but every other `UnsafeExpressionError` names only the construct: a disallowed
node or call at validation, a method called on a value that is no string at evaluation. In a
configuration holding many expressions, `Function 'eval' is not allowed` does not say which
one called it. Since BUG-135, a runtime failure quotes its expression
([resolution.md](../../architecture/expressions/resolution.md#an-evaluation-failure-names-its-expression)),
so the refusals are now the odd ones out. Fix direction: one site words the quote, as
`_eval_expr` does for runtime failures. That site would be the validation loop in
`resolve_expressions` for the static refusals and `_eval_expr` for the receiver check.

```python
from confarg.dictexpr import resolve_expressions

for v in ("${n.upper()}", "${s.upper() + eval('1')}", "${s[0:1]}", "${s.upper(}"):
    try:
        resolve_expressions({"n": 1, "s": "x", "v": v})
    except Exception as exc:
        print(f"{v}: {type(exc).__name__}: {exc}")
# expected: each one quotes its expression, as the syntax refusal quotes its body
# actual:
# ${n.upper()}: UnsafeExpressionError: Method 'upper' is called on a int; it is allowed only on a string
# ${s.upper() + eval('1')}: UnsafeExpressionError: Function 'eval' is not allowed
# ${s[0:1]}: UnsafeExpressionError: Disallowed construct in expression: Slice
# ${s.upper(}: UnsafeExpressionError: Invalid expression syntax: 's.upper('
```

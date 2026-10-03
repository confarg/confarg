# BUG-129 — A syntax error quotes the anchor stand-in names, not the expression as written

**Where:** `src/confarg/dictexpr/_expressions.py` (`resolve_expressions`, `_validate_ast`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** behavior

`resolve_expressions` swaps every anchor marker for a stand-in name (`.x` → `__UP1__.x`,
`::x` → `__ROOT__.x`) before anything parses
([reference-anchoring.md#implementation-constraints](../../architecture/expressions/reference-anchoring.md#implementation-constraints)),
and `_validate_ast` quotes the text it was handed. So the `Invalid expression syntax` message for
a malformed anchored expression shows names the user never wrote and that no documentation
mentions.

Fix direction: quote the body as written. `_unname_anchor` already inverts the naming lexically,
so the message can be built from `_unname_anchor(expr_str)`, or validation can be handed the raw
body beside the named one.

```python
from confarg.dictexpr import resolve_expressions
from confarg.exceptions import ConfargError

for data in [{"a": {"x": 1, "p": "${.x +}"}}, {"x": 1, "p": "${::x +}"}]:
    try:
        resolve_expressions(data)
    except ConfargError as exc:
        print(type(exc).__name__, exc)
# expected: UnsafeExpressionError Invalid expression syntax: '.x +'
#           UnsafeExpressionError Invalid expression syntax: '::x +'
# actual:   UnsafeExpressionError Invalid expression syntax: '__UP1__.x +'
#           UnsafeExpressionError Invalid expression syntax: '__ROOT__.x +'
```

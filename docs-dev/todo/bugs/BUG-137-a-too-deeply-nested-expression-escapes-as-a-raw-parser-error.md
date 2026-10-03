# BUG-137 — A too deeply nested expression escapes as a raw parser error

**Where:** `src/confarg/dictexpr/_expressions.py` (`_parse_expression`, `_validate_ast`,
`_extract_references`, `_prefix_content`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** high · **Impact:** behavior

Every parse site treats a body that does not parse as a `SyntaxError`. Validation refuses it as
`UnsafeExpressionError`, while reference extraction and mounting skip it
([limitations.md#expressions](../../architecture/limitations.md#expressions)). But Python's parser
gives up on a deeply nested body in two other ways: a `RecursionError` while it builds the tree,
and a `MemoryError` when its own stack overflows. Neither is caught, so a configuration value
such as `${------…a}` crashes `resolve()` with no `ConfargError` and no quote of the expression.
A file mounted below the root crashes `merge()` the same way, through `_prefix_content`. Python
documents the same failure for `ast.literal_eval` and `compile()` on untrusted input. Fix
direction: `_parse_expression`, the one parse every site goes through, reports both as the
`SyntaxError` the sites already handle, so validation refuses the body as written.

```python
from confarg.dictexpr import resolve_expressions

for n in (5000, 100000):
    try:
        resolve_expressions({"a": 1, "v": "${" + "-" * n + "a}"})
    except Exception as exc:
        print(n, type(exc).__name__, exc)
# expected: UnsafeExpressionError naming the expression, as for any body that does not parse
# actual:
# 5000 RecursionError maximum recursion depth exceeded during ast construction
# 100000 MemoryError Parser stack overflowed - Python source too complex to parse
```

# BUG-126 — An anchor marker cannot be followed by a subscript

**Where:** `src/confarg/dictexpr/_expressions.py` (`_name_anchor`, `_AnchorResolver`) ·
**Filed:** 2026-10-03
**Effort:** M · **Risk:** medium · **Impact:** behavior

A dot and a constant subscript each spell one path segment
([values-and-references.md#spelling-a-path](../../architecture/expressions/values-and-references.md#spelling-a-path)),
and the subscript is the only spelling of a key that is no identifier or of a list index. After
an anchor marker it is not available: `_name_anchor` always swaps the marker for a stand-in
*followed by a dot* (`.` → `__UP1__.`), so `${.['web-1']}` and `${.[0]}` become
`__UP1__.['web-1']` and `__UP1__.[0]`, which do not parse. A node-relative reference can
therefore reach neither a sibling key such as `web-1` nor a sibling list element, and the
`_AnchorResolver.visit_Name` branch that rewrites a bare stand-in is unreachable.

Fix direction: let the stand-in own the dot only when an identifier follows it, so `.[0]`
becomes `__UP1__[0]`, which `_attribute_chain` already reads as a path.

```python
from confarg.dictexpr import resolve_expressions

print(resolve_expressions({"svc": {"web-1": 5, "port": "${.['web-1']}"}}))
# expected: {'svc': {'web-1': 5, 'port': 5}}
# actual:   UnsafeExpressionError: Invalid expression syntax: "__UP1__.['web-1']"

print(resolve_expressions({"xs": [1, "${.[0]}"]}))
# expected: {'xs': [1, 1]}
# actual:   UnsafeExpressionError: Invalid expression syntax: '__UP1__.[0]'
```

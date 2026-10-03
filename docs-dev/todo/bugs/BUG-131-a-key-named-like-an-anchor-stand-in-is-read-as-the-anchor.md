# BUG-131 — A key named like an anchor stand-in is read as the anchor

**Where:** `src/confarg/dictexpr/_expressions.py` (`_name_anchor`, `_AnchorResolver`,
`_Prefixer`, `_collect_names`) ·
**Filed:** 2026-10-03
**Effort:** M · **Risk:** high · **Impact:** behavior

Anchor markers are swapped for the stand-in names `__ROOT__` and `__UP<n>__` so the body parses,
and everything downstream recognises an anchor by that name alone
([reference-anchoring.md#implementation-constraints](../../architecture/expressions/reference-anchoring.md#implementation-constraints)).
A name the user wrote with the same spelling is therefore an anchor too: `${__ROOT__.x}` reads
the root's `x`, not the key `__ROOT__`, and `${__UP1__.x}` reads a sibling. Since BUG-126 a bare
`${__ROOT__}` reads the root whole, a cycle, where it used to read the key by accident. Nothing
says these names are reserved, and no other dunder name is refused as a reference base.

Fix direction needs a decision: refuse a written stand-in name lexically before naming (as
reserved, the way `__include__` is), or name markers with something no body can spell. The
second is the stronger guarantee, but every stand-in must still parse as a Python name.

```python
from confarg.dictexpr import resolve_expressions

print(resolve_expressions({"__ROOT__": {"x": 1}, "a": {"p": "${__ROOT__.x}"}, "x": 2})["a"])
print(resolve_expressions({"__UP1__": {"x": 1}, "a": {"x": 2, "p": "${__UP1__.x}"}})["a"])
# expected: {'p': 1} and {'x': 2, 'p': 1}, the keys the names spell (or a refusal naming them)
# actual:   {'p': 2} and {'x': 2, 'p': 2}
```

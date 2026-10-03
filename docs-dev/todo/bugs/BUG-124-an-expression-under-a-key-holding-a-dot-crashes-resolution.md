# BUG-124 — An expression under a key holding a dot crashes resolution

**Where:** `src/confarg/dictexpr/_expressions.py` (`_scan_expressions`, `_set_nested_by_path`,
`_anchor_prefix`) ·
**Filed:** 2026-10-03
**Effort:** M · **Risk:** medium · **Impact:** behavior

`dictexpr` names an expression's position by a dotted string, joining keys with `.` in the scan
and splitting on it again to write the result back. A key that holds a dot (`example.com`, which
any format can spell as a quoted key) is then two segments: writing back raises a raw `KeyError`,
and `_anchor_prefix` would climb the wrong number of levels from such a node. Reading a value
under that key works since BUG-121, because evaluation walks segments without re-splitting them
([values-and-references.md#spelling-a-path](../../architecture/expressions/values-and-references.md#spelling-a-path)).
The same joining also lets `a.b` (nested) and `a.b` (one key) share one graph node.

Fix direction: carry an expression's position as a tuple of segments through the scan, the
graph, `_set_nested_by_path` and `_anchor_prefix`, as `_get_nested` already takes them.

```python
from confarg.dictexpr import resolve_expressions

print(resolve_expressions({"a.b": "${x}", "x": 1}))
# expected: {'a.b': 1, 'x': 1}
# actual:   KeyError: 'a'
```

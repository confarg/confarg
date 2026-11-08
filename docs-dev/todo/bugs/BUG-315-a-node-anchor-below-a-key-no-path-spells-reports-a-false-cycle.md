---
filed: 2026-11-08
where:
  - src/confarg/dictexpr/_expressions.py::_key_segment  # a bool, a float or any other constant key spells no segment
  - src/confarg/dictexpr/_expressions.py::_segment_link  # spells a position's segment back as a constant subscript
  - src/confarg/dictexpr/_expressions.py::_path_to_ast
effort: M  # the design pass: may a constant subscript of such a key spell a segment?
needs_design: true
risk: high  # the expression engine, on every channel
impact: behavior  # an anchor that fails today resolves
severity: major  # a valid reference fails loudly, and a date or None key has no absolute spelling to fall back on
introduced_by: [BUG-127]  # spelled an anchor's position back as an expression, which reads no such key
---

# BUG-315 — A node anchor below a key no path spells reports a false cycle

A node anchor written below a dict key that is neither text nor an integer, `${.a}` inside `{True: {a: 1, b: …}}`, a float, `None` or a date key alike, is refused as `CircularReferenceError: Circular reference detected among: m.True.b`.
Resolution spells the anchor's position back as an expression (`_path_to_ast`, [reference anchoring](../../architecture/expressions/reference-anchoring.md#implementation-constraints)), which writes such a key as a constant subscript; `_key_segment` reads that constant as no segment ([spelling a path](../../architecture/expressions/values-and-references.md#spelling-a-path): "a bool, a float or any other key is no segment"), so the reference reads `m` whole through Python's subscript, and `m` holds the expression itself.
Such a key comes from a caller's dict or a tagged YAML key (`!!bool`, `!!float`, `!!null`, `!!timestamp`); an integer key is reached by its digits (BUG-311).

Fix direction, for the design pass: let a constant subscript a position spells name its key exactly, an anchor's spelling only, so the walk reaches it as the scan names it; or let an anchor carry its position as segments rather than spell it back as source, which `_unparse` also needs for a message (an `ast.Constant` holding a date unparses as a call).

Origin: a regression from BUG-127, which spelled a document's prefix and a dot run's path by `_path_to_ast`, segment by segment; BUG-124, just before it, had held a position as a tuple of the keys the data holds, and the same anchor resolved.
`_spells_as_name` asked `isidentifier()` of each segment, an `AttributeError` for a key that is no text; later revisions turned that into a `TypeError` in `_list_index` (BUG-133) and the false cycle above.

```python
import datetime

from confarg.dictexpr import resolve_expressions

for key in (True, 1.5, None, datetime.date(2020, 1, 1)):
    try:
        print(repr(key), resolve_expressions({"m": {key: {"a": 1, "b": "${.a}"}}}))
    except Exception as e:
        print(repr(key), f"{type(e).__name__}: {e}")
# expected: each prints {'m': {<key>: {'a': 1, 'b': 1}}}
# actual:   True CircularReferenceError: Circular reference detected among: m.True.b
#           1.5 CircularReferenceError: Circular reference detected among: m.1.5.b
#           None CircularReferenceError: Circular reference detected among: m.None.b
#           datetime.date(2020, 1, 1) CircularReferenceError: Circular reference detected among: m.2020-01-01.b
```

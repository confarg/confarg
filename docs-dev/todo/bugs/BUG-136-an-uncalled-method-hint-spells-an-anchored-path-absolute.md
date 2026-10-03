# BUG-136 — The uncalled-method hint spells an anchored path as an absolute one

**Where:** `src/confarg/dictexpr/_expressions.py` (`_eval_path_or`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** high · **Impact:** behavior

When a dot names a string method without calling it, `_eval_path_or` hints at the call with
`ast.unparse(node)`. That is the tree after `_AnchorResolver` turned the anchor into the node's
absolute path, so `${.n.upper}` in a list element is told to write `xs[0].n.upper(...)`. That
spelling pins the element to its index, which is exactly what
[reference-anchoring.md#a-relative-reference-is-never-serialized-as-an-absolute-path](../../architecture/expressions/reference-anchoring.md#a-relative-reference-is-never-serialized-as-an-absolute-path)
says a relative reference must never turn into. Since BUG-129 every other message quotes the
expression as written
([reference-anchoring.md#implementation-constraints](../../architecture/expressions/reference-anchoring.md#implementation-constraints)).
The `Field 'xs.0.n.upper'` part is right: a field is named by its absolute path everywhere.
Fix direction: build the callee's text from the body as written. The resolver keeps each node's
source offsets, so `ast.get_source_segment` on the named body, un-named, should give it *(inferred)*.

```python
from confarg.dictexpr import resolve_expressions

try:
    resolve_expressions({"xs": [{"n": "s", "p": "${.n.upper}"}]})
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
# expected: ... 'upper' is a method only when called, as in .n.upper(...)
# actual:   MissingReferenceError: Field 'xs.0.n.upper' not found: 'upper' is a method only when called, as in xs[0].n.upper(...)
```

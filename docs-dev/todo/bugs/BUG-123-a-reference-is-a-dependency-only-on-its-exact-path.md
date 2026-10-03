# BUG-123 — A reference is a dependency only on its exact path

**Where:** `src/confarg/dictexpr/_expressions.py` (`resolve_expressions`, step 3) ·
**Filed:** 2026-10-03
**Effort:** M · **Risk:** medium · **Impact:** behavior

`resolve_expressions` keeps a reference as a graph edge only when it equals an expression's
path (`deps[path] = refs & expr_paths`). Three spellings read an expression without naming its
exact path, so when the referencing value sorts first it reads the expression unresolved:

- **a whole subtree** holding one: `${svc}` while `svc.h` is `${base}`. A pure `${svc}` hides it
  only because it substitutes the live sub-dict, filled in later
  ([values-and-references.md#referencing-a-whole-subtree](../../architecture/expressions/values-and-references.md#referencing-a-whole-subtree));
  an interpolation stringifies it on the spot and the raw `${base}` lands in the result;
- **a negative index**: `${xs[-1]}` records `xs.-1`, while the scan names the element `xs.0`;
- **a path through an expression's value**: `${a.b.c}` while `a.b` is `${d}`.

Fix direction: an expression path is a dependency of a reference when either is a prefix of the
other (segment-wise), and a negative index is normalized against the list's length at
extraction, when the data is at hand
([resolution.md#resolution-algorithm](../../architecture/expressions/resolution.md#resolution-algorithm)).
A reference to an ancestor from inside it (`svc.a: ${svc}`) then becomes the cycle it is.

```python
from confarg.dictexpr import resolve_expressions

print(resolve_expressions({"v": "s=${svc}", "svc": {"h": "${base}"}, "base": 1})["v"])
# expected: s={'h': 1}
# actual:   s={'h': '${base}'}

print(resolve_expressions({"v": "${xs[-1]}", "xs": ["${base}"], "base": "b"})["v"])
# expected: b
# actual:   ${base}

print(resolve_expressions({"v": "${a.b.c}", "a": {"b": "${d}"}, "d": {"c": 1}})["v"])
# expected: 1
# actual:   MissingReferenceError: Field 'a.b.c' not found: cannot traverse into str
```

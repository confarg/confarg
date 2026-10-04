# BUG-134 — A miss off a value no path names is a bare repr

**Where:** `src/confarg/dictexpr/_expressions.py` (`_eval_path_or`) · **Filed:** 2026-10-03
**Effort:** S · **Risk:** high · **Impact:** behavior

When no config path answers a dot or a subscript, `_eval_path_or` falls back on Python's subscript
([values-and-references.md#spelling-a-path](../../architecture/expressions/values-and-references.md#spelling-a-path)).
If that fails too and the node spells no path, it re-raises Python's error, and `_eval_expr`
wraps it into an `ExpressionEvalError` whose message is the bare `KeyError` repr. Two cases spell
no path, even after BUG-128 made a computed key spell one: a base that is not rooted at a name
(`${(a if c else b)['x']}`, `${(a if c else b).x}`), and a key that is no segment (`${m[flag]}`
with `flag: false`). The message then reads `'x'` or `False`, with nothing to say that a key is
missing. Fix direction: word the miss in `_eval_path_or`, e.g. `Key 'x' not found in the value of
(a if c else b)`, and keep `ExpressionEvalError`, since there is no field to name. Moving it to
`MissingReferenceError` would raise the impact to `api`.

```python
from confarg.dictexpr import resolve_expressions

for v in ("${(a if c else a)['x']}", "${m[f]}", "${a.x}"):
    try:
        resolve_expressions({"a": {"y": 1}, "c": True, "m": {True: 1}, "f": False, "v": v})
    except Exception as exc:
        print(f"{v}: {type(exc).__name__}: {exc}")
# expected: each miss says which key is missing, as ${a.x}'s does
# actual:
# ${(a if c else a)['x']}: ExpressionEvalError: Error in expression "${(a if c else a)['x']}": 'x'
# ${m[f]}: ExpressionEvalError: Error in expression '${m[f]}': False
# ${a.x}: MissingReferenceError: Field 'a.x' not found in configuration
```

# BUG-128 — A computed subscript's miss is a bare `KeyError`

**Where:** `src/confarg/dictexpr/_expressions.py` (`_eval_path_or`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** api

A miss on a path is reported as a missing field rather than a `KeyError`
([safety-model.md#safety-model](../../architecture/expressions/safety-model.md#safety-model),
[values-and-references.md#spelling-a-path](../../architecture/expressions/values-and-references.md#spelling-a-path)).
A computed subscript (`${svc[k]}`) spells no path, so `_eval_path_or` has no miss of its own to
report: it re-raises Python's error and `_eval_expr` wraps it as `ExpressionEvalError`, whose
message is the bare `KeyError` repr, `'nope'`. The same miss is a `MissingReferenceError` naming
the field when the key is a constant, so the error class a caller catches depends on how the key
was spelled. A dot off a computed base (`${svc[k].nope}`) misses the same way since BUG-125 made
it a subscript.

Fix direction: once the computed key is evaluated, the path is known (`svc` plus the key), so the
fallback's miss can be reported as `MissingReferenceError.field_not_found` on that path, through
`_step` like any other read. Moving from `ExpressionEvalError` to `MissingReferenceError` changes
the exception type a caller catches, hence the impact.

```python
from confarg.dictexpr import resolve_expressions

for v in ("${svc['nope']}", "${svc[k]}"):
    try:
        resolve_expressions({"svc": {"web": 1}, "k": "nope", "v": v})
    except Exception as exc:
        print(f"{v}: {type(exc).__name__}: {exc}")
# expected: ${svc[k]}: MissingReferenceError: Field 'svc.nope' not found in configuration
# actual:
# ${svc['nope']}: MissingReferenceError: Field 'svc.nope' not found in configuration
# ${svc[k]}: ExpressionEvalError: Error in expression '${svc[k]}': 'nope'
```

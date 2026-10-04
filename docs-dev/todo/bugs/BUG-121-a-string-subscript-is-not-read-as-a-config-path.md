# BUG-121 — A string subscript is not read as a config path

**Where:** `src/confarg/dictexpr/_expressions.py` (`_attribute_chain`, `_collect_names`,
`_eval_attribute`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** medium · **Impact:** behavior

`_attribute_chain` reads only integer subscripts as path segments, so `svc['web']` is not a path.
Two consequences:

- **The dependency is missed.** `_collect_names` records the base `svc`, which is no expression
  path, so no graph edge reaches `svc.web.host`. When the referencing value sorts first, it reads
  the referenced expression unresolved and the raw `${...}` text lands in the result.
- **An attribute after it fails.** `svc['web'].host` evaluates the subscript to a dict, then
  falls back to `getattr` on it.

A string subscript is also the only spelling that could reach a key that is no identifier
(`svc['web-1']`), which the dotted form cannot express
([reference-anchoring.md#implementation-constraints](../../architecture/expressions/reference-anchoring.md#implementation-constraints)).
Fix direction: read a string-constant subscript as a path segment in `_attribute_chain`, so
extraction, evaluation and prefixing share it
([resolution.md#resolution-algorithm](../../architecture/expressions/resolution.md#resolution-algorithm)).

```python
from confarg.dictexpr import resolve_expressions

data = {"v": "${svc['web']['host']}", "svc": {"web": {"host": "${base}.x"}}, "base": "b"}
print(resolve_expressions(data)["v"])
# expected: b.x
# actual:   ${base}.x

print(resolve_expressions({"svc": {"web": {"host": "h"}}, "v": "${svc['web'].host}"})["v"])
# expected: h
# actual:   ExpressionEvalError: Error in expression "${svc['web'].host}": 'dict' object has no attribute 'host'
```

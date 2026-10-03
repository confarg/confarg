# BUG-125 — A method named without a call yields the bound method

**Where:** `src/confarg/dictexpr/_expressions.py` (`_eval_path_or`, `_eval_attribute`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** medium · **Impact:** behavior

When no config path answers `a.b`, `_eval_attribute` falls back on `getattr` on the evaluated
receiver, with only dunders refused. A string has no attribute that is not a method, so on a
string the fallback only ever yields a bound method: `${name.upper}` is the method object, and an
interpolation prints `<built-in method upper of str object at 0x…>` — the silent leak BUG-120
removed for a bare function name
([safety-model.md#a-function-is-named-only-by-a-call](../../architecture/expressions/safety-model.md#a-function-is-named-only-by-a-call)).
On any other receiver the fallback reaches every public attribute by name, whatever the type:
`${p.unlink}` on a `pathlib.Path` value hands the bound method to construction, where a
`Callable` field would accept it. A method may only be called, and only on a string
([safety-model.md#a-method-is-a-string-method](../../architecture/expressions/safety-model.md#a-method-is-a-string-method));
naming one without a call has no use in a config value.

Fix direction: decide what the attribute fallback is for. Either refuse a callable result (the
bound method) as `UnsafeExpressionError`, keeping data attributes such as a date's `year`; or
drop the fallback for attributes altogether, so an attribute no path answers is a missing field.
Precedent: CEL and JMESPath expose fields of the data only, never host-language attributes.

```python
from confarg.dictexpr import resolve_expressions

print(resolve_expressions({"n": "abc", "v": "x=${n.upper}"})["v"])
# expected: an error naming 'upper' as a method that must be called
# actual:   x=<built-in method upper of str object at 0x00007FFA215B4BB0>
```

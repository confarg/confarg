# BUG-122 — A method call is whitelisted by name alone, free-function names included

**Where:** `src/confarg/dictexpr/_expressions.py` (`_validate_call`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** medium · **Impact:** behavior

The safety model admits calls to whitelisted free functions and *string methods*
([safety-model.md#safety-model](../../architecture/expressions/safety-model.md#safety-model)).
`_validate_call` instead accepts an attribute call whose name is in `_SAFE_METHODS` **or
`_SAFE_FUNCTIONS`**, on any receiver. So `x.max(...)`, `x.round()`, `x.int()` and the rest pass
validation although no string has such a method, and a non-string value can be called through
them: `Decimal.max`, or a YAML date's `replace`. On a string the call fails later, as a missing
field rather than as `Method 'max' is not allowed`. Fix direction: drop `_SAFE_FUNCTIONS` from
the method test, and decide whether a whitelisted method may run on a non-`str` receiver; if not,
refuse it at evaluation, since the receiver's type is not known at validation.

```python
from decimal import Decimal

from confarg.dictexpr import resolve_expressions

print(resolve_expressions({"d": Decimal("1"), "m": "${d.max(5)}"})["m"])
# expected: UnsafeExpressionError: Method 'max' is not allowed
# actual:   5
```

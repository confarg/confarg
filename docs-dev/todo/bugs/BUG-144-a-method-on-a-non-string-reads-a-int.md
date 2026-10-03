# BUG-144 — The refusal of a method on a non-string reads "a int"

**Where:** `src/confarg/dictexpr/_expressions.py` (`_eval_method`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** behavior

`_eval_method` words its refusal as `called on a {type(receiver).__name__}`, which reads
`a int` for an integer receiver. The YAML values most likely to reach it are integers, so the
wrong article is also the common case. `dictexpr` cannot import `_types._src_type`
([messages-live-on-exceptions.md](../../architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)).
Fix direction: name the type without an article (`called on an object of type 'int'`), or pick
the article from the name.

```python
from confarg.dictexpr import resolve_expressions

try:
    resolve_expressions({"n": 1, "v": "${n.upper()}"})
except Exception as exc:
    print(exc)
# expected: Method 'upper' is called on an int; it is allowed only on a string
# actual:   Method 'upper' is called on a int; it is allowed only on a string
```

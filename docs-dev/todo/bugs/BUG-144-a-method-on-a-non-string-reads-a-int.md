---
filed: 2026-10-03
where:
  - src/confarg/dictexpr/_expressions.py::_eval_method
effort: S
risk: low
impact: behavior
severity: minor
introduced_by: [BUG-122]  # PR-281, which wrote the message
---
# BUG-144 — The refusal of a method on a non-string reads "a int"

`_eval_method` words its refusal as `called on a {type(receiver).__name__}`, which reads
`a int` for an integer receiver. The YAML values most likely to reach it are integers, so the
wrong article is also the common case. `dictexpr` cannot import `_types._src_type`
([messages-live-on-exceptions.md](../../architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)).
Fix direction: name the type without an article (`called on an object of type 'int'`), or pick
the article from the name.

Origin: latent since BUG-122's fix, which introduced this refusal when it limited methods to
strings, with the article fixed to `a`.

```python
from confarg.dictexpr import resolve_expressions

try:
    resolve_expressions({"n": 1, "v": "${n.upper()}"})
except Exception as exc:
    print(exc)
# expected: Method 'upper' is called on an int; it is allowed only on a string
# actual:   Method 'upper' is called on a int; it is allowed only on a string
```

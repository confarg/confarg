# BUG-139 — A form feed in an expression shifts its anchor markers

**Where:** `src/confarg/dictexpr/_expressions.py` (`_line_starts`, `_significant_tokens`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** high · **Impact:** behavior

`_significant_tokens` turns the tokenizer's (row, column) into an offset in the body, using
the line starts `_line_starts` computes with `str.splitlines`. That splits at a form feed,
`\x1c`–`\x1e`, `\x85`, U+2028 and U+2029 as well, while the tokenizer counts a row only at
`\n`, `\r\n` or `\r`. So in a body that has one of those characters before a line break, every
marker on a later row is edited at the wrong offset. `_name_anchor` then garbles the body
(`(.y +\x0c\n .x)` becomes `(__UP1__.y +\x0c\n__UP1__..x)`), and `_strip_anchor`, which
`merge()` runs, cuts the wrong characters (`(::y +\x0c\n ::x)` becomes
`(y +\x0c\n:x)`). A form feed is whitespace to Python. Fix direction: split lines as the
tokenizer does. REF-54's rewrite of `_line_starts` must keep that rule.

```python
from confarg.dictexpr import resolve_expressions

for sep in ("\n", "\x0c\n"):
    try:
        print(repr(sep), resolve_expressions({"a": {"x": 1, "y": 2, "p": "${(.y +" + sep + " .x)}"}})["a"]["p"])
    except Exception as exc:
        print(repr(sep), type(exc).__name__, exc)
# expected: '\n' 3 and '\x0c\n' 3, as eval("(1 +\x0c\n 2)") is 3
# actual:
# '\n' 3
# '\x0c\n' UnsafeExpressionError Invalid expression syntax: '(.y +\x0c\n .x)'
```

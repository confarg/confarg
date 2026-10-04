# BUG-130 — A malformed expression in an included file crashes `merge()` with a raw `SyntaxError`

**Where:** `src/confarg/dictexpr/_expressions.py` (`_prefix_content`, `prefix_references`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** medium · **Impact:** behavior

The merge layer does not validate expressions: a malformed one is carried through `merge()` and
refused by `resolve()` as an `UnsafeExpressionError` quoting it
([invariants.md#merge-stays-unvalidated](../../architecture/invariants.md#merge-stays-unvalidated),
[limitations.md#expressions](../../architecture/limitations.md#expressions)). That holds for a
file loaded at the root, but a file mounted below it has its bare references prefixed while it
loads, and `_prefix_content` parses each body with no guard. The `SyntaxError` escapes `merge()`
itself, as no `ConfargError`, and names neither the file nor the expression.

Fix direction: leave a body that does not parse unprefixed, as `_extract_references` and
`_anchor_markers` already skip one, so validation reports it later with its own message.

```python
import pathlib, tempfile
from typing import Any
import confarg
from confarg.exceptions import ConfargError

tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "frag.yaml").write_text("p: 1\nq: ${p +}\n")
(tmp / "main.yaml").write_text("db: {__include__: frag.yaml}\n")
for path in ["frag.yaml", "main.yaml"]:
    try:
        merged = confarg.merge(dict[str, Any], files=[str(tmp / path)], argv=[])
        confarg.resolve(merged)
    except ConfargError as exc:
        print(path, "->", type(exc).__name__, exc)
    except SyntaxError as exc:
        print(path, "-> raw", type(exc).__name__, exc)
# expected: main.yaml -> UnsafeExpressionError Invalid expression syntax: 'db.p +' (or 'p +')
# actual:
# frag.yaml -> UnsafeExpressionError Invalid expression syntax: 'p +'
# main.yaml -> raw SyntaxError invalid syntax (<unknown>, line 1)
```

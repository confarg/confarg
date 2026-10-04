# BUG-145 — An expression that parses but nests past the recursion limit crashes the walkers

**Where:** `src/confarg/dictexpr/_expressions.py` (`_parse_expression`, `_collect_names`,
`_Prefixer`, `_AnchorResolver`, `_unparse`, `_evaluate_ast`) · **Filed:** 2026-10-03
**Effort:** M · **Risk:** high · **Impact:** behavior

BUG-137 made a body too deep for Python's *parser* a body that does not parse. A shallower body
still parses, a few hundred to a few thousand levels depending on the Python version, but every
step after the parse walks the tree recursively in Python: `_collect_names`, `copy.deepcopy`,
the `NodeTransformer`s, `ast.unparse` and the evaluator. Past `sys.getrecursionlimit()` they raise
a raw `RecursionError`: `resolve()` from reference extraction at depth 1000, and a mounting
`merge()` from `_prefix_content` already at depth 500. Between the two, validation accepts the
body and evaluation fails on it, so the outcome also depends on how deep the caller's own stack
is. Fix direction: `_parse_expression` bounds the depth of the tree it returns and refuses a
deeper one as `_TooDeepError`, the error BUG-137 added
([resolution.md#resolution-algorithm](../../architecture/expressions/resolution.md#resolution-algorithm)).
Then no walker ever sees a tree it cannot recurse through, and `resolve()` and `merge()` agree
on which bodies parse. The bound is the decision to record. For precedents, CPython's tokenizer
caps nested brackets at 200, `serde_json` caps recursion at 128, and Go's `regexp/syntax` caps
nesting at 1000. A bound below what works today, about 300 levels in `resolve()`, would turn
`behavior` into `config`.

```python
import pathlib
import tempfile
from typing import Any

import confarg

for n in (500, 1000):
    try:
        confarg.resolve({"a": 1, "v": "${" + "-" * n + "a}"})
    except Exception as exc:
        print("resolve", n, type(exc).__name__, str(exc)[-40:])

frag = pathlib.Path(tempfile.mkdtemp(), "frag.yaml")
frag.write_text("a: 1\nv: ${" + "-" * 500 + "a}\n")
try:
    confarg.merge(dict[str, Any], argv=["--config.db", str(frag)], env={})
except Exception as exc:
    print("merge", 500, type(exc).__name__, exc)
# expected: UnsafeExpressionError naming the expression, from validation, at every depth
# actual (Python 3.12):
# resolve 500 ExpressionEvalError ---a}': maximum recursion depth exceeded
# resolve 1000 RecursionError maximum recursion depth exceeded
# merge 500 RecursionError maximum recursion depth exceeded
```

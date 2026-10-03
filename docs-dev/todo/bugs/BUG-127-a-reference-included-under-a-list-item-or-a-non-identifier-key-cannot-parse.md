# BUG-127 — A reference included under a list item or a non-identifier key cannot parse

**Where:** `src/confarg/dictexpr/_expressions.py` (`prefix_references`, `_Prefixer`,
`_path_to_ast`), `src/confarg/_files.py` (`_resolve_dict`, `_resolve_list`) ·
**Filed:** 2026-10-03
**Effort:** M · **Risk:** high · **Impact:** behavior

An included document's bare references are prefixed by where the include sits in the including
file ([reference-anchoring.md#why-the-node-anchor-resolves-late](../../architecture/expressions/reference-anchoring.md#why-the-node-anchor-resolves-late)).
`_Prefixer` builds that prefix as an attribute chain and `ast.unparse` writes it back as text, so
a segment that is no identifier comes out as Python that does not mean the path: a list index
(`xs.0.p`, a syntax error), a key with a hyphen (`web-1.p`, a subtraction), and a key holding a
dot (`h.com.p`, read as three segments). The prefix also reaches `prefix_references` as a dotted
string, which `_files` joins from the segments it now holds, so a key holding a dot is split
before `_Prefixer` even sees it. Every include into a list item that holds a bare reference
fails this way.

Fix direction: pass the prefix as a tuple of segments (`path_in_file` already is one, and the
mount subpath of `_files._mount` can become one), and have `_Prefixer` spell a segment that is
no identifier as a constant subscript (`xs[0].p`, `['web-1'].p`, `['h.com'].p`), which
`_attribute_chain` reads back as the same path
([values-and-references.md#spelling-a-path](../../architecture/expressions/values-and-references.md#spelling-a-path)).

```python
import pathlib, tempfile
from typing import Any
import confarg
from confarg.exceptions import ConfargError

tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "frag.yaml").write_text("p: 1\nq: ${p}\n")
for mount in ["xs: [{__include__: frag.yaml}]", "web-1: {__include__: frag.yaml}", "'h.com': {__include__: frag.yaml}"]:
    (tmp / "main.yaml").write_text(mount + "\n")
    merged = confarg.merge(dict[str, Any], files=[str(tmp / "main.yaml")], argv=[])
    try:
        print(merged, "->", confarg.resolve(merged))
    except ConfargError as exc:
        print(merged, "->", type(exc).__name__, exc)
# expected: q resolves to 1 under each mount
# actual:
# {'xs': [{'p': 1, 'q': '${xs.0.p}'}]} -> UnsafeExpressionError Invalid expression syntax: 'xs.0.p'
# {'web-1': {'p': 1, 'q': '${web-1.p}'}} -> UnsafeExpressionError Invalid expression syntax: 'web-1.p'
# {'h.com': {'p': 1, 'q': '${h.com.p}'}} -> MissingReferenceError Field 'h' not found in configuration
```

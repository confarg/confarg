# BUG-132 — A name Python normalizes reads another key

**Where:** `src/confarg/dictexpr/_expressions.py` (`_validate_ast`, `_parse_expression`) ·
**Filed:** 2026-10-03
**Effort:** M · **Risk:** high · **Impact:** config

Python's parser NFKC-normalizes every identifier (PEP 3131), so a name or a dotted segment in an
expression reads the normalized key, not the one written: `${ﬁle}` (with the `ﬁ` ligature) reads
`file`, silently, even when the configuration holds both keys. The subscript spelling is not
normalized and reads the right key, which is why `_path_to_ast` already refuses to write such a
segment with a dot (BUG-127,
[reference-anchoring.md#implementation-constraints](../../architecture/expressions/reference-anchoring.md#implementation-constraints)).
A path written by the user gets no such care
([values-and-references.md#spelling-a-path](../../architecture/expressions/values-and-references.md#spelling-a-path)).

Fix direction needs a decision: refuse a name the tokenizer sees as not NFKC-stable, pointing at
the subscript spelling, or keep the raw token's text as the segment. Precedents differ: Python
normalizes, while JavaScript compares identifiers exactly as written.

```python
from confarg.dictexpr import resolve_expressions

data = {"file": "plain", "ﬁle": "ligature", "v": "${ﬁle}", "w": "${::['ﬁle']}"}
print(ascii(resolve_expressions(data)))
# expected: v and w both 'ligature', the key the name spells (or a refusal naming it)
# actual:   {'file': 'plain', 'ﬁle': 'ligature', 'v': 'plain', 'w': 'ligature'}
```

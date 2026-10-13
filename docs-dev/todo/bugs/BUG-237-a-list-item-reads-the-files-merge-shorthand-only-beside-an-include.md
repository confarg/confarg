---
filed: 2026-10-13
where:
  - src/confarg/_merge.py::_normalize_merge_ops  # "list items are left untouched"
  - src/confarg/_files.py::_resolve_node  # a list item's include merges its siblings, which normalizes them
effort: S
risk: medium
impact: behavior
severity: minor  # one spelling errors loudly, the other works; nothing is silently wrong
introduced_by: [PR-5]  # list items skipped by the normalization; siblings of an include merged by the merge that normalizes
---
# BUG-237 — A list item reads the files' merge shorthand only beside an include

`_normalize_merge_ops` leaves list items untouched, so in a file `rows: [{k: 4, j: 9, k-: null}]` keeps `k-` as a key and construction refuses it as an unknown field. Give the same item through an include, `rows: [{__include__: row.yaml, k-: null}]`, and the item's sibling keys are merged over the included part by `_merge._merge_within_source`, which normalizes them: `k-` becomes a delete, and the row builds with `k` at its default. A list item has no layer below it, so the delete can only ever act on the item's own included part ([deep merge](../../architecture/pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too)). The two spellings should agree. Either list items read the shorthand like any dict of a file does (and `key+:`, `"N-":` and the reserved op keys with it), or an include's siblings in a list item stop reading it.

Origin: latent since the initial version (PR-5). Its `_normalize_merge_ops` skipped list items, while its `_resolve_dict` merged an include's siblings over the included dict with `_deep_merge`, which normalizes both sides wherever they stand. Found fixing BUG-227, which kept the siblings' merge reading the shorthand and drops the deletes it keeps for the layers below once they stand in a list item.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class Row:
    k: int = 0
    j: int = 0


@dataclass
class Config:
    rows: list[Row] = field(default_factory=list)


d = Path(tempfile.mkdtemp())
(d / "row.yaml").write_text("k: 4\nj: 9\n")
(d / "flat.yaml").write_text("rows:\n  - {k: 4, j: 9, k-: null}\n")
(d / "inc.yaml").write_text("rows:\n  - {__include__: row.yaml, k-: null}\n")
for top in ("flat.yaml", "inc.yaml"):
    try:
        print(confarg.load(Config, argv=[], files=[str(d / top)], env={}))
    except Exception as e:
        print(f"{type(e).__name__}: {e}")

# expected: the same outcome twice
# actual:   TypeCoercionError: Unknown field(s) ['k-'] for Row at 'rows[0]'. Valid fields: ['j', 'k']
#           Config(rows=[Row(k=0, j=9)])
```

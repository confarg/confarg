---
filed: 2026-11-02
where:
  - src/confarg/typedload/_construct.py::_construct_union_by_tag  # hands the dict, the tag still spelled union_tag, to the spec reader
  - src/confarg/typedload/_construct.py::_construct_any  # reads the literal `class` opener only
effort: S
risk: medium  # the hand-off is shared by the Callable and the Any variant
impact: config  # an Any variant holding the dict today would hold the object the tag names
severity: critical  # the Any variant holds the raw dict, the tag's module imported, with no error
introduced_by: [FEAT-42, BUG-234]  # PR-414: an Any variant reads the tag as its spec; PR-446: a Callable variant too
---

# BUG-305 — A custom union tag reaches a spec reader it does not open

With a `union_tag` other than `class`, a union whose tag names no struct variant hands the dict to its Callable or `Any` variant as that variant's spec ([a Callable beside another variant](../../architecture/callables.md#a-callable-beside-another-variant)), the key still spelled as the tag, while a spec reader opens on the literal `class`.
`int | Any` imports the class `{Kind: collections.OrderedDict}` names, then holds the dict as it is; `int | Callable[..., Any]` refuses it, saying the dict must hold one of `bind`, `class`, `call` or `classfn`, which says nothing of `Kind`.
The same value spelled `{class: collections.OrderedDict}` builds the object, `class` being an opener wherever it is not the union tag.
Fix direction: the spec the reader is handed spells the tag as the `class` opener it names, so the variant builds the class the tag imported, as the callables note documents.

Origin: FEAT-42 (PR-414) let an `Any` variant read a class no struct variant holds as its spec, handing it the dict as written; BUG-234 (PR-446) extended the hand-off to a Callable variant.
Both were tested with the default tag, the one spelling under which the tag and the opener coincide; latent since FEAT-42.
Found fixing BUG-303, which reads the same union tag.

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import confarg
import confarg.exceptions


@dataclass
class C:
    a: int | Any = 0
    c: int | Callable[..., Any] = 0


for data in (
    {"a": {"Kind": "collections.OrderedDict"}},
    {"a": {"class": "collections.OrderedDict"}},
    {"c": {"Kind": "collections.OrderedDict"}},
):
    try:
        print(data, "->", confarg.build(C, data, union_tag="Kind"))
    except confarg.exceptions.ConfargError as e:
        print(data, "->", type(e).__name__, e)

# expected: a=OrderedDict() for both spellings of 'a', and c built from the spec as with 'class'
# actual:   {'a': {'Kind': 'collections.OrderedDict'}} -> C(a={'Kind': 'collections.OrderedDict'}, c=0)
#           {'a': {'class': 'collections.OrderedDict'}} -> C(a=OrderedDict(), c=0)
#           {'c': {'Kind': 'collections.OrderedDict'}} -> TypeCoercionError Callable dict at 'c' must specify one of 'bind', 'class', 'call' or 'classfn'
```

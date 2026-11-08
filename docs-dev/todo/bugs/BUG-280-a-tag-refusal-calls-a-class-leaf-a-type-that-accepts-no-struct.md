---
filed: 2026-10-25
where:
  - src/confarg/exceptions.py  # TypeCoercionError.tag_selects_no_struct holds the text
  - src/confarg/typedload/_construct.py::_tag_selects_no_struct
effort: S
risk: low  # the refusal's text is pinned by tests/typedload/test_construct.py::_no_struct_refusal
impact: behavior  # the message only
severity: minor  # a misleading message: the refusal is right, its reason names a word the user docs never use
introduced_by: [BUG-188, BUG-252]  # PR-370 wrote the leaf's text; the BUG-252 fix gave it to a union of leaves
---

# BUG-280 — A tag refusal calls a class leaf a type that "accepts no struct"

A `class` tag on a field no tag can select is refused with `<type> accepts no struct, so the tag cannot select one` ([a tag no variant takes](../../architecture/types/construction.md#a-tag-no-variant-takes)).
The refusal is right, but its reason rests on "struct", confarg's internal word for a class built from fields, which `docs/` and the README never use.
It reads worst where the type is a class: a `datetime` field, or an `int | datetime` one, told that `datetime` "accepts no struct" when the tag names `datetime` itself.
What the user needs to hear is that `datetime` is built from one value, not from fields, which the message's `call:` pointer already assumes.
Fix direction: say why in the user's terms (built from one value, not from fields), in `tag_selects_no_struct`, which spells the text for both the leaf and the union.
The tests pin `Path` and `int | Path` but no registered leaf, where the sentence reads worst.
Found in the review of the revision that fixed BUG-195, BUG-252 and BUG-256.

Origin: BUG-188 (PR-370) wrote the text for a class tag on a scalar field, where the type was mostly `int` or `str` and "struct" read as the field's annotation's word; BUG-252 routed a union of leaves to the same text, so the union now says it too.
Latent since BUG-188 for a class leaf such as `datetime`.

```python
from dataclasses import dataclass
from datetime import datetime

import confarg


@dataclass
class A:
    when: datetime = datetime(2026, 1, 1)


@dataclass
class B:
    when: int | datetime = 0


for cls in (A, B):
    try:
        print(confarg.from_dict(cls, {"when": {"class": "datetime.datetime"}}))
    except Exception as e:
        print(f"{type(e).__name__}: {e}")

# expected: the same refusal, saying datetime is built from one value, not from fields
# actual:
# TypeCoercionError: Cannot coerce dict {'class': 'datetime.datetime'} to datetime at 'when'. The 'class' key is the union tag, which names a subclass of a struct-typed field's annotation; datetime accepts no struct, so the tag cannot select one. A 'call:' spec computes a value the field's type accepts.
# TypeCoercionError: Cannot coerce dict {'class': 'datetime.datetime'} to int | datetime at 'when'. The 'class' key is the union tag, which names a subclass of a struct-typed field's annotation; int | datetime accepts no struct, so the tag cannot select one. A 'call:' spec computes a value the field's type accepts.
```

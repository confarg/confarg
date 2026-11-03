---
filed: 2026-11-02
where:
  - src/confarg/_types.py::_is_plain_class  # a class whose constructor signature reads, a C type's included
  - tests/typedload/test_construct.py::TestATagNoVariantTakes  # pins datetime as a leaf built from one value
  - tests/typedload/test_construct.py::TestATagSpelledKeyIsDataWhereNoTagSelects
effort: M
needs_design: true  # whether a C type CPython gives a signature reads as a struct, so a tag opens it, or stays a leaf on every Python
risk: medium  # the struct test is asked by every walk; a registered leaf's shape changes on one interpreter only
impact: config  # one of the two readings changes what a dict under a datetime field means on some interpreter
severity: major  # a dict variant's `class` entry is refused as a class key on 3.15, loudly, with no workaround since REF-121 fixed the key's spelling
introduced_by: [BUG-280, BUG-276]  # the tests pinning datetime as a leaf no tag opens, written when 3.15 support landed
---

# BUG-306 — A C type reads as a struct on Python 3.15, where it gains a signature

On Python 3.15 `inspect.signature(datetime.datetime)` reads `(year, month, day, hour=0, …, *, fold=0)`, where 3.14 and earlier find none, so `_is_plain_class` takes `datetime` for a plain class and a registered leaf a tag opens ([an explicit tag opts a leaf back in](../../architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)).
The same configuration then means two things by interpreter: `{class: datetime.datetime, year: 2026, month: 1, day: 2}` builds a `datetime` on 3.15 and is refused on 3.14, and `{class: confidential}` under `int | datetime | dict[str, str]` is the dict variant's entry on 3.14 and a tag that fails to import on 3.15 ([where no tag selects](../../architecture/types/construction.md#where-no-tag-selects-a-variant-that-reads-a-dict-holds-the-key-as-data)).
Three tests of `tests/typedload/test_construct.py` pin the 3.14 reading and fail on 3.15: `TestATagNoVariantTakes::test_the_refusal_says_why_no_class_is_picked[registered-leaf]` and `[registered-leaf-variant]`, and `TestATagSpelledKeyIsDataWhereNoTagSelects::test_a_dict_variant_holds_the_key[registered-leaf-built-from-one-value]`.
Fix direction, for the design pass: either a type registered with a coercion stays a leaf a tag does not open whatever signature the interpreter gives it, so a C type reads the same on every Python, or the reading follows the signature and the tests pin a leaf no interpreter gives one; every other C type CPython gains a signature for meets the same question.

Origin: BUG-280 and BUG-276 wrote the tests around `datetime` as a leaf built from one value, true of every interpreter but 3.15, whose support landed the same day; the struct test has read a class by its constructor signature since plain classes were structs, so the drift is CPython's, met first on 3.15.
Found fixing BUG-303, running the touched tests on 3.15.

```python
import sys
from dataclasses import dataclass
from datetime import datetime

import confarg
import confarg.exceptions


@dataclass
class C:
    when: datetime | None = None
    labels: int | datetime | dict[str, str] = 0


print(sys.version_info[:2])
for data in (
    {"when": {"class": "datetime.datetime", "year": 2026, "month": 1, "day": 2}},
    {"labels": {"class": "confidential"}},
):
    try:
        print(data, "->", confarg.build(C, data))
    except confarg.exceptions.ConfargError as e:
        print(data, "->", type(e).__name__, e)

# expected: the same two lines on every Python
# actual, 3.14:
#   {'when': {...}} -> TypeCoercionError Cannot coerce dict {'class': 'datetime.datetime', 'year': 2026, 'month': 1, 'day': 2} to datetime at 'when'. The 'class' key picks the class to build from the keys beside it, and datetime is built from one value, not from keys. A 'call:' spec computes a value the field's type accepts.
#   {'labels': {'class': 'confidential'}} -> C(when=None, labels={'class': 'confidential'})
# actual, 3.15:
#   {'when': {...}} -> C(when=datetime.datetime(2026, 1, 2, 0, 0), labels=0)
#   {'labels': {'class': 'confidential'}} -> TypeCoercionError Cannot import class 'confidential' from the 'class' key at 'labels': Cannot import 'confidential': no importable module found in path. The value must be a full dotted path, e.g. 'mypackage.mymodule.MyClass'.
```

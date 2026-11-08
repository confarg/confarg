---
filed: 2026-10-24
where:
  - src/confarg/typedload/_construct.py::_construct_union  # the union tag is routed before any variant reads the dict
  - src/confarg/typedload/_construct.py::reads_as_new_value  # a union of several members: the tag replaces
effort: S
needs_design: true  # the effort sizes the design pass: when a dict variant wins the tag's spelling
risk: medium  # the merge's replace-or-refine table and the CLI walk read the tag the same way
impact: behavior
severity: minor  # loud; an application can pass a union_tag no data key spells
introduced_by: [PR-5]  # the initial union construction routes the tag before any variant
---

# BUG-276 — A union with a dict variant reads a `class` key as the tag, where a lone dict holds it as data

A `dict[str, str]` field holds `{class: confidential}` as an entry, as [the type decides](../../architecture/design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines) says a dict does.
Add a variant beside it and the key becomes the union tag: `int | dict[str, str]` refuses the value as a tag no variant takes ([a tag no variant takes](../../architecture/types/construction.md#a-tag-no-variant-takes)), and `Job | dict[str, str]` imports `confidential` as a class and refuses it.
Every channel agrees, argv's `--labels.class confidential` included, so the configuration has no spelling of that entry in such a field; the application's only way out is a `union_tag` no data key spells.
Design question: when does a dict variant win the tag's spelling?
For instance, a union with no variant a tag can select reads the key as data (the merge's table and the CLI walk changing with it), and a union with one reads a tag that imports no class as data for its dict variant, which would make a typo in a tag silently a dict entry.
Found while fixing BUG-252, which gave the first case its refusal.

Origin: latent since the initial version (PR-5), whose `_construct_union` routed a dict holding the union tag to the tag before any variant could read it, whatever the variants were; the lone dict field never looked at the tag.

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class Job:
    kind: str = "batch"


@dataclass
class D:
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class UD:
    labels: int | dict[str, str] = 0


@dataclass
class JD:
    labels: Job | dict[str, str] = field(default_factory=dict)


for C in (D, UD, JD):
    try:
        print(confarg.from_dict(C, {"labels": {"class": "confidential"}}))
    except Exception as e:
        print(f"{type(e).__name__}: {e}")

# expected: D(labels={'class': 'confidential'}), and UD and JD holding the same dict, or a design that says why not
# actual:
# D(labels={'class': 'confidential'})
# TypeCoercionError: Cannot coerce dict {'class': 'confidential'} to int | dict[str, str] at 'labels'. The 'class' key is the union tag, which names a subclass of a struct-typed field's annotation; int | dict[str, str] accepts no struct, so the tag cannot select one. A 'call:' spec computes a value the field's type accepts.
# TypeCoercionError: Cannot import class 'confidential' from 'class' tag at 'labels': Cannot import 'confidential': no importable module found in path. The value must be a full dotted path, e.g. 'mypackage.mymodule.MyClass'.
```

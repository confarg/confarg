# BUG-103 — A subclass-only field named like the tag loses its value to the tag at construction

**Where:** `src/confarg/_parse_cli.py` (`_resolve_field_type`, via `_subclass_field_type`) and
`src/confarg/typedload/_construct.py` (`_construct_struct_dispatch`) · **Filed:** 2026-10-01
**Effort:** S · **Risk:** low · **Impact:** config

The walk treats a subclass-only field as a member (`_advance_field_type` asks
`_subclass_field_type`), so under the real-field-wins rule a subclass-only field spelled
exactly like the tag wins the tag's spelling at parse time — while construction's shadowing
predicate asks the base's own fields only, so it still reads the merged key as the tag and
imports the field's value as a class path. The value the user set for the field is stripped
by `_construct_by_class_path`, and the failure names the very flag the user did set.
Pre-existing before BUG-102 (the tag then won at parse too, so the key was the tag's either
way); it surfaced while fixing BUG-102 because the walk and the predicate now disagree. The
fix direction: make the two agree — either the predicate includes subclass-only fields
(the walk's answer, and the field then constructs through the named subclass), or the walk's
member attempt skips them for the tag question. A decision is needed first, on the same
ground as
[casts-and-reserved-words.md#real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins).

```python
from dataclasses import dataclass

import confarg


@dataclass
class Base:
    pass


@dataclass
class Sub(Base):
    Kind: str


print(confarg.load(Base, argv=["--Kind", "__main__.Sub"], union_tag="Kind"))
# expected: Sub(Kind='__main__.Sub') — or a documented precedence that names the collision
# actual:   confarg.exceptions.MissingFieldError: Missing required field 'Kind' of type
#           <class 'str'>. Set it via CLI (--Kind), environment variable, or config file.
```

# BUG-83 — Without a class tag, the adapters drop a subclass's flags outright

**Where:** `src/confarg/cli/_collect.py` (`_collect_ns_inheritance`, the `class_tag is None`
early return) ·
**Filed:** 2026-09-30
**Effort:** S · **Risk:** medium · **Impact:** behavior

The no-tag half of the shape BUG-69 fixed for the tag-present case: on a base class with
subclasses and no `--class` anywhere, `_collect_ns_inheritance` returns before any descent, so
a subclass's flag registered in the flat namespace never reaches the merged dict. Vanilla
coerces it through
[`_subclass_field_type`](../../architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags)
and keeps it, for `build()` to judge; the union-field branch already collects every variant's
fields when no tag is present, and so does the union-root collector — the inheritance branch
alone stops at the early return. Both `build()` outcomes agree here (no discriminator, either
way), so the defect is the merged dict `merge()` — a public API — returns.

Fix direction: the same answer the union-field branch gives without a tag — descend into
`_dataclass_subclasses(tp)`, one decision shared with `_collect_named_variant`'s sibling walk.
Found while fixing BUG-69, which scoped itself to the tag-present branches.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Base:
    pass


@dataclass
class Sub1(Base):
    a: int = 1


@dataclass
class Sub2(Base):
    b: int = 2


ARGV = ["--b", "5"]
for label, merged in (
    ("vanilla", confarg.merge(Base, argv=ARGV, env={})),
    ("argparse", merge_namespace(Base, make_parser(Base, argv=ARGV).parse_args(ARGV), argv=ARGV, env={})),
):
    print(f"{label} merged: {merged!r}")

# expected: both front-ends merge {'b': 5} — vanilla coerces 'b' by Sub2's field type
# actual:
#   vanilla merged: {'b': 5}
#   argparse merged: {}
```

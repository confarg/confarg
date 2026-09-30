# BUG-86 — A subclass's override of a base-declared field is coerced by the last subclass walk

**Where:** `src/confarg/cli/_collect.py` (`_collect_ns_inheritance` walks every subclass with
its own field types; the vanilla rule is `src/confarg/_parse_cli.py` `_advance_field_type`,
which answers a base-declared field by the **base's own** annotation and consults
`_subclass_field_type` only for a subclass-only name) · **Filed:** 2026-09-30
**Effort:** M · **Risk:** medium · **Impact:** behavior

When a subclass overrides a field the base class declares, vanilla resolves the flag by the
base's own field type — `_advance_field_type` finds the name in the base's fields and never
reaches the subclasses. The adapters' inheritance walks descend into every subclass *after*
walking the base, and each re-collects the inherited field by the subclass's overriding type,
so the last subclass's coercion overwrites the base's (and the other subclasses') — the
inheritance shape of the last-write-wins family BUG-84 fixed for union variants, but with a
different vanilla answer: the base's type, not the common-or-`str` rule. Fix direction: the
subclass walks should not re-collect a field the base's own walk already collected by the
base's type — walk only the subclass's declared delta, or coerce by the base's annotation.
Found while fixing BUG-84.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Base:
    a: int = 1


@dataclass
class SubSame(Base):
    pass


@dataclass
class SubOverride(Base):
    a: float = 2.0  # type: ignore[assignment]


@dataclass
class Holder:
    x: Base = None


argv = ["--x.a", "7"]
van = confarg.merge(Holder, argv=argv, env={})
ns = make_parser(Holder, argv=argv).parse_args(argv)
arg = merge_namespace(Holder, ns, argv=argv, env={})
print(f"vanilla: {van!r}")
print(f"argparse: {arg!r}")

# expected (vanilla, coerced by the base's declared int):
#   vanilla: {'x': {'a': 7}}
# actual (argparse, the last subclass walk's coercion):
#   argparse: {'x': {'a': 7.0}}
```

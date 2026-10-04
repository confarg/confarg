# BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters

**Where:** `src/confarg/cli/_collect.py` (`_disagreeing_owner_flags`) · static registration
of subclass fields in `src/confarg/cli/_build.py` · **Filed:** 2026-10-01
**Effort:** M · **Risk:** medium · **Impact:** behavior

When subclasses disagree on a field's type, vanilla's walk answers `str` for that field
(`_types._subclass_field_type`). A path continuing below it then resolves to nothing, so
`--item.inner.a` is an unknown argument. The adapters register each subclass's fields
separately, so the framework accepts the flag. The collector then decides conflicts in
`_disagreeing_owner_flags`, which resolves the *whole* path inside each variant and compares
the results. `inner.a` is `int` in both, so it reports no conflict, and the flag is
collected. That function is also the third inline copy of the "common type if every owner
agrees, else `str`" rule, beside `_resolve_union_field_type` and `_subclass_field_type`.
Unlike the walk, it compares only at the end of the path.

Fix direction: answer with the walk itself. Ask `_resolve_field_type` of the container for
the full path, and treat a `None` answer as vanilla's refusal and `str` as a conflict.
Registration should refuse what that walk refuses. See
[cli-adapters/union-inheritance-and-cast-flags.md](../../architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags)
and
[invariants.md#delegate-to-the-canonical-function](../../architecture/invariants.md#delegate-to-the-canonical-function).
Cyclopts cannot register this target at all (BUG-114).

```python
from dataclasses import dataclass, field

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class A:
    a: int = 0


@dataclass
class B:
    a: int = 0
    b: str = ""


@dataclass
class Base:
    pass


@dataclass
class S1(Base):
    inner: A = field(default_factory=A)


@dataclass
class S2(Base):
    inner: B = field(default_factory=B)


@dataclass
class Cfg:
    item: Base = field(default_factory=Base)


argv = ["--item.inner.a", "5"]
try:
    print(f"vanilla:  {confarg.merge(Cfg, argv=argv, env={})!r}")
except Exception as e:
    print(f"vanilla:  {type(e).__name__}: {e}")
ns = make_parser(Cfg, argv=argv).parse_args(argv)
print(f"argparse: {merge_namespace(Cfg, ns, argv=argv, env={})!r}")

# expected: both front-ends refuse the path
#   vanilla:  UnknownArgumentError: Unknown argument: '--item.inner.a' (field 'item.inner.a' not found)
# actual (click and typer agree with argparse):
#   vanilla:  UnknownArgumentError: Unknown argument: '--item.inner.a' (field 'item.inner.a' not found)
#   argparse: {'item': {'inner': {'a': 5}}}
```

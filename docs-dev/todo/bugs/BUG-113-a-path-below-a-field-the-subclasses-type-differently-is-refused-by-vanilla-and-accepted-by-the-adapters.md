# BUG-113 — A path below a field the subclasses type differently is refused by vanilla and accepted by the adapters

**Where:** static registration of subclass fields in `src/confarg/cli/_build.py` ·
**Filed:** 2026-10-01
**Effort:** M · **Risk:** medium · **Impact:** behavior

When subclasses disagree on a field's type, vanilla's walk answers `str` for that field
(`_types._subclass_field_type`). A path continuing below it then resolves to nothing, so
`--item.inner.a` is an unknown argument. The adapters register each subclass's fields
separately, so the framework accepts the flag. Since REF-72 the adapters' CLI channel is
vanilla's loop, which then refuses it with vanilla's own `UnknownArgumentError` — at merge,
after the framework's parse, so `--help` still lists a flag that cannot be used and the refusal
comes late. Before REF-72 the collector wrote the value instead.

Fix direction: registration should refuse what the walk refuses — ask `_resolve_field_type` of
the container for the full path and register nothing where it answers `None`. See
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
print("argparse: parse_args accepted the flag")
try:
    print(f"argparse: {merge_namespace(Cfg, ns, argv=argv, env={})!r}")
except Exception as e:
    print(f"argparse: {type(e).__name__} at merge: {e}")

# expected: argparse refuses the flag in parse_args, as it refuses every flag vanilla refuses
# actual (click and typer agree with argparse):
#   vanilla:  UnknownArgumentError: Unknown argument: '--item.inner.a' (field 'item.inner.a' not found)
#   argparse: parse_args accepted the flag
#   argparse: UnknownArgumentError at merge: Unknown argument: '--item.inner.a' (field 'item.inner.a' not found)
```

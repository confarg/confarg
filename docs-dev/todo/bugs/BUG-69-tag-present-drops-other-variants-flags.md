# BUG-69 — With a class tag present, the adapters drop the other variants' flags

**Where:** `src/confarg/cli/_collect.py` (`_collect_named_variant`, both tag branches) ·
**Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

When a tag names a variant, `_collect_named_variant` descends only into the named struct, so a
flag of a *different* variant or subclass at the same path vanishes from the adapters' merged
dict. Vanilla keeps every argv flag — coerced by whichever variant owns the name — and lets
`build()` reject the stray one, so
[byte-identity](../../architecture/cli-adapters/parity.md#byte-identical-merged-dicts) is broken;
a union-root target is unaffected, because its collector descends into all variants whatever
the tag says. The loud case: with a *valid* tag, a mistyped `--<field>` is silently ignored and
the wrong-variant field never reaches the user, where vanilla raises
`Unknown field(s) [...]`. The quiet case: with a tag whose import fails (BUG-45's shape), the
sibling flags vanish from the merged dict that `merge()` — a public API — returns, while
vanilla keeps them next to the raw tag.

Fix direction: with a tag present, collect the non-named variants' flags too, the way vanilla
does — one decision in `_collect_named_variant`, so the union-field branch, the inheritance
branch and every front-end inherit it. The coercion of a stray flag (its own variant's field
type, as vanilla coerces it) is the part to get exactly right.

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


ARGV = ["--class", f"{__name__}.Sub1", "--b", "5"]

for label, merged in (
    ("vanilla", confarg.merge(Base, argv=ARGV, env={})),
    ("argparse", merge_namespace(Base, make_parser(Base, argv=ARGV).parse_args(ARGV), argv=ARGV, env={})),
):
    print(f"{label} merged: {merged!r}")
    try:
        print(f"{label} build:  ", confarg.build(Base, merged))
    except Exception as e:  # noqa: BLE001
        print(f"{label} build:  {type(e).__name__}: {e}")

# expected: both front-ends merge {'class': '...Sub1', 'b': 5} and both build() reject 'b'
# actual:
#   vanilla merged: {'class': '__main__.Sub1', 'b': 5}
#   vanilla build:  TypeCoercionError: Unknown field(s) ['b'] for Sub1 at ''.
#                   Valid fields: ['a']
#   argparse merged: {'class': '__main__.Sub1'}
#   argparse build:   Sub1(a=1)
```

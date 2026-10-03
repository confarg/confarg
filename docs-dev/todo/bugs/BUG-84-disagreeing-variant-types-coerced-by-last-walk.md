# BUG-84 — A flag owned by disagreeing variants is coerced by the last walk, not by vanilla's rule

**Where:** `src/confarg/cli/_collect.py` (the per-variant walks: `_collect_ns_union_field`'s
loop and `_collect_variant_fields`, the shared walk every tag and no-tag branch descends
through); the vanilla rule is
`src/confarg/_parse_cli.py` (`_resolve_union_field_type`, `_subclass_field_type`) ·
**Filed:** 2026-09-30
**Effort:** M · **Risk:** medium · **Impact:** behavior

When several variants own the same flag name with *different* field types, vanilla coerces the
token once, by the common type when every owner agrees and by `str` when they disagree; the
adapters' collector instead walks each variant in turn and lets the last write win, so the
merged dict holds that variant's coercion. Byte-identity is broken in both spellings: without a
tag the last variant in the union wins; with a tag, the re-dispatch inside each sibling walk
(`_collect_ns_inheritance` reads the tag again with the sibling as base) leaves the *named*
variant's coercion standing. The no-tag shape predates BUG-69's fix; the tag shape rides on it.
Both sides usually agree again after `build()`, so the defect is the value `merge()` — a public
API — returns, and any `${...}` expression reading the field.

Fix direction: reproduce vanilla's common-type-or-str answer for a flag with several owners —
the rule itself is
[parity](../../architecture/cli-adapters/parity.md#byte-identical-merged-dicts), not a new
decision; where to compute it in a type-walk collector is. Found while fixing BUG-69.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Sub1b:
    a: int = 1


@dataclass
class Sub2b:
    a: float = 2.0


@dataclass
class Holder:
    x: "Sub1b | Sub2b" = None


for label, argv in (
    ("no tag", ["--x.a", "7"]),
    ("tag   ", ["--x.class", f"{__name__}.Sub1b", "--x.a", "7"]),
):
    van = confarg.merge(Holder, argv=argv, env={})
    ns = make_parser(Holder, argv=argv).parse_args(argv)
    arg = merge_namespace(Holder, ns, argv=argv, env={})
    print(f"{label} vanilla: {van!r}  argparse: {arg!r}")

# expected: 'a' merges as the string '7' on every front-end — vanilla returns str
#   when the variants disagree about a field's type
# actual:
#   no tag vanilla: {'x': {'a': '7'}}  argparse: {'x': {'a': 7.0}}
#   tag    vanilla: {'x': {'class': '__main__.Sub1b', 'a': '7'}}
#          argparse: {'x': {'class': '__main__.Sub1b', 'a': 7}}
```

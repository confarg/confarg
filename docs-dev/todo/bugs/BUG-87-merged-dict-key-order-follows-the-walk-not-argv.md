# BUG-87 — The adapters' merged dict orders keys by the walk, not by argv, so a dump differs byte for byte

**Where:** `src/confarg/cli/_collect.py` (the type walk's write order: a tag's write-back vs
the fields' collection, a bare flag vs its sub-flags); the argv-order reader precedents are
`cli/_collect._arity_flag_writes_last` and `_tokens_past_whole_field_delete` · **Filed:**
2026-09-30
**Effort:** M · **Risk:** medium · **Impact:** behavior

`merge()` on an adapter returns a dict equal to vanilla's but with the keys in walk order,
while vanilla writes in argv order — so `parity.md`'s byte-identity holds for the values and
breaks for the serialization: a dump of the merged dict, or any consumer sensitive to key
order, differs between the front-ends for the same command line. Two shapes show it: a union
tag spelled after its variants' flags (the tag is written back before the descent), and an
inheritance tag spelled before them (the base's fields are collected before
`_collect_ns_inheritance` reads the tag). The fix direction is an argv-order reader like the
other two, deciding which of the related writes is the later argv occurrence. Found while
fixing BUG-84; BUG-85 is the value-level member of the same family.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class V1:
    a: int = 1


@dataclass
class V2:
    b: int = 2


@dataclass
class Holder:
    u: "V1 | V2 | None" = None


argv = ["--u.a", "7", "--u.class", f"{__name__}.V1"]
van = confarg.merge(Holder, argv=argv, env={})
ns = make_parser(Holder, argv=argv).parse_args(argv)
arg = merge_namespace(Holder, ns, argv=argv, env={})
print(f"vanilla: {van!r}")
print(f"argparse: {arg!r}")

# expected: the same key order vanilla writes — argv spells --u.a first
#   vanilla: {'u': {'a': 7, 'class': '__main__.V1'}}
# actual: the walk writes the tag back first
#   argparse: {'u': {'class': '__main__.V1', 'a': 7}}
```

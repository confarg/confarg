# BUG-111 — A bare flag between its sub-flags keeps the sub-flags before it on the adapters

**Where:** `src/confarg/cli/_collect.py` (`_arity_flag_writes_last` and its callers: the
namedtuple, struct, registered-leaf and union branches of `_collect_field`,
`_collect_ns_optional_seq`, `_collect_variant_fields`) · **Filed:** 2026-10-01
**Effort:** L · **Risk:** medium · **Impact:** behavior

Vanilla writes flags in argv order, so in `--pt.x 1 --pt 7 8 --pt.y 2` the bare `--pt`
drops the `x` before it and `--pt.y` refines what `--pt` left. The adapters decide with
`_arity_flag_writes_last`, which only asks whether the *last* bare occurrence follows
*every* sub-flag. That is a summary of the order, and it cannot describe interleaving: the bare
flag is not last, so every sub-flag is laid over it, the superseded `--pt.x 1` included. On a
namedtuple the built object differs (`x=1` where vanilla builds `x=7`); on a struct the
merged dict keeps a key vanilla dropped. All four adapters behave the same way (observed through the contract-suite
loaders; argparse shown below).
[namedtuple-arity-flag-argv-order.md](../../architecture/design-decisions/namedtuple-arity-flag-argv-order.md)
claims byte-identical dicts on all five front-ends for this rule, which is wrong in this case.

Fix direction: no finer reader. Make the order decision vanilla's own loop
(REF-72), which writes each occurrence where argv puts it.

```python
from dataclasses import dataclass, field
from typing import NamedTuple

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


class Pt(NamedTuple):
    x: int = 0
    y: int = 0


@dataclass
class Inner:
    a: int = 0
    b: int = 0


@dataclass
class Cfg:
    pt: Pt = Pt()
    s: Inner = field(default_factory=Inner)


for argv in (["--pt.x", "1", "--pt", "7", "8", "--pt.y", "2"], ["--s.a", "1", "--s", '{"b": 5}', "--s.b", "2"]):
    van = confarg.merge(Cfg, argv=argv, env={})
    ns = make_parser(Cfg, argv=argv).parse_args(argv)
    arg = merge_namespace(Cfg, ns, argv=argv, env={})
    print(f"vanilla:  {van!r}")
    print(f"argparse: {arg!r}")

# expected (vanilla, the bare flag erases what came before it):
#   vanilla:  {'pt': {'x': 7, 'y': 2}}
#   vanilla:  {'s': {'b': 2}}
# actual (argparse; click, typer and cyclopts agree with it):
#   argparse: {'pt': {'x': 1, 'y': 2}}
#   argparse: {'s': {'b': 2, 'a': 1}}
```

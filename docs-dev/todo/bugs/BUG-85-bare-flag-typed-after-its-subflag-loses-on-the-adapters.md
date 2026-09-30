# BUG-85 — A struct field's bare flag typed after its sub-flag loses to the sub-flag on the adapters

**Where:** `src/confarg/cli/_collect.py` (`_collect_field`'s struct branch stores the bare
value before it descends, so a sub-flag's write always lands *on top of* it; vanilla's parse
loop writes in argv order) · **Filed:** 2026-09-30
**Effort:** M · **Risk:** medium · **Impact:** behavior

Vanilla applies the flags in the order the user typed them, so a bare `--<field> <scalar>`
typed after a `--<field>.<sub>` flag replaces the whole subtree with the scalar. The adapters'
collector walks the type tree, and its bare-value store always precedes its descent into the
sub-flags, so the sub-flag's write wins no matter how argv spelled the two — the merged dict
keeps the sub-flag's dict where vanilla keeps the bare scalar. The same inversion surrounds
every related-write pair the collector makes (a scalar force-cast flag vs the bare flag, the
disagreeing-owner raw store of BUG-84 vs the walks below it); argv already decides such
questions elsewhere
([whole-value flags](../../architecture/cli-adapters/whole-value-flags.md#whole-value-flags),
`_arity_flag_writes_last`), and this is the same shape of reader. Found while fixing BUG-84.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Inner:
    b: int = 0


@dataclass
class Mid:
    a: Inner = None


@dataclass
class Holder:
    x: Mid = None


argv = ["--x.a.b", "7", "--x.a", "9"]
van = confarg.merge(Holder, argv=argv, env={})
ns = make_parser(Holder, argv=argv).parse_args(argv)
arg = merge_namespace(Holder, ns, argv=argv, env={})
print(f"vanilla: {van!r}")
print(f"argparse: {arg!r}")

# expected (vanilla, last write in argv order):
#   vanilla: {'x': {'a': '9'}}
# actual (argparse; the reversed argv spelling agrees on both):
#   argparse: {'x': {'a': {'b': 7}}}
```

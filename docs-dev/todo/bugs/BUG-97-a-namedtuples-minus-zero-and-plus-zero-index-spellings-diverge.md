# BUG-97 — A namedtuple's -0 and +0 index spellings diverge across the front-ends

**Where:** `src/confarg/cli/_build.py` (`_collect_namedtuple_specs`) · **Filed:** 2026-09-30
**Effort:** S · **Risk:** low · **Impact:** behavior

Found while fixing BUG-80 (closed). The negative spellings BUG-80 registered are `i` and
`i - n`, so `-1..-n` — but vanilla's type walk accepts *any* segment `int()` parses in
range, and build resolves it the same way, so two odd spellings slip through on vanilla
only:

- `--pt.-0`: vanilla parses it and `build()` resolves `-0` to field `0` (BUG-80's
  `_indexed_dict_to_positions` does `int("-0") == 0`), so it *works* on vanilla while
  every adapter refuses the unregistered flag at parse. A plain fixed tuple does not
  share the gap: its element flags register from argv, and the patch scan accepts
  `--lang.-0` there too.
- `--pt.+0`: vanilla parses it (`int("+0") == 0` in the walk) and `build()` refuses it
  as `Unknown field(s) ['+0']`; the adapters refuse at parse. The merged dicts can never
  agree, the
  [byte-identical rule](../../architecture/cli-adapters/parity.md#byte-identical-merged-dicts)
  again.

Fix direction is a maintainer's choice: refuse the odd spellings in vanilla's type walk
(`_advance_field_type` treats `-0` and `+N` as out-of-model, all five agreeing at parse),
or register them and let `build()` own the refusal (`-0` resolving, `+N` refused) — the
first reading has precedent on its side: an index spelling is `-?\d+`, nothing else.

```python
from dataclasses import dataclass
from typing import NamedTuple
import confarg
from confarg.cli.argparse import make_parser, merge_namespace


class Point(NamedTuple):
    x: int = 0
    y: int = 0


@dataclass
class T:
    pt: Point = Point(0, 0)


argv = ["--pt.-0", "7"]
print("vanilla :", confarg.merge(T, argv=argv, env={}), "->", confarg.load(T, argv=argv, env={}))
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))

# expected: the two front-ends agree
# actual:
#   vanilla : {'pt': {'-0': 7}} -> T(pt=Point(x=7, y=0))
#   argparse: SystemExit 2 — "unrecognized arguments: --pt.-0 7"
#   --pt.+0: vanilla merge gives {'pt': {'+0': 7}}, load raises
#   TypeCoercionError "Unknown field(s) ['+0']", argparse SystemExit 2
```

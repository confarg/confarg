# BUG-66 — A namedtuple's arity flag and sub-flags merge differently in the adapters and vanilla

**Where:** `src/confarg/cli/_collect.py` (`_collect_ns_namedtuple`) ·
`src/confarg/_merge.py` (`_set_nested`) · **Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

Found while fixing BUG-59 (closed);
a design decision, not a mechanical fix, so it is filed rather than widened into.

When the arity flag and a sub-flag both fill a namedtuple, the two halves merge differently on
the two sides. The adapters merge positionally into `{name: value}` — the arity tokens fill the
positions no sub-flag took, whichever order the flags arrived in. Vanilla is order-dependent:
the arity flag first stores a list, and `_set_nested` then promotes it to a
`LIST_REPLACE_BASE_KEY` base so the sub-flag rides along (`{'*': [1, 2], 'y': 9}`); the sub-flag
*first* is a dict the arity flag's `_set_nested` then replaces wholesale, so `--pt.y` is
silently dropped. Both orders break the
[byte-identical](../../architecture/04-cli-adapters.md#byte-identical-merged-dicts) rule, and
vanilla's second order looks wrong in its own right — a flag the user typed vanishing is worse
than a shape mismatch. Which shape is intended is for the maintainer: the adapter's
order-independent merge reads like the better contract, but adopting it means changing vanilla
(`_set_nested`'s promotion, or the namedtuple branch of `_consume_fixed_tuple_args`), so the
decision belongs in
[10-design-decisions.md](../../architecture/10-design-decisions.md) before either side moves.

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


for argv in (["--pt", "1", "2", "--pt.y", "9"], ["--pt.y", "9", "--pt", "1", "2"]):
    parser = make_parser(T, argv=argv)
    print("argv    :", argv)
    print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
    print("vanilla :", confarg.merge(T, argv=argv, env={}))

# expected: for each order, the two merged dicts are equal
# actual:
#   argv    : ['--pt', '1', '2', '--pt.y', '9']
#   argparse: {'pt': {'x': 1, 'y': '9'}}
#   vanilla : {'pt': {'*': [1, 2], 'y': 9}}
#   argv    : ['--pt.y', '9', '--pt', '1', '2']
#   argparse: {'pt': {'x': 1, 'y': '9'}}
#   vanilla : {'pt': [1, 2]}
```

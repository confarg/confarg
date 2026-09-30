# BUG-65 — An index sub-flag is renamed and dropped in the adapters

**Where:** `src/confarg/cli/_collect.py` (`_namedtuple_sub_flags`) · **Filed:** 2026-09-29
**Effort:** S · **Risk:** medium · **Impact:** behavior

Found while fixing BUG-59 (closed);
filed separately because the defect is the *shape* of the collected dict, not the types — the
type half of the same site was BUG-64, closed with BUG-66, so the values below now arrive
coerced while the keys still do not.

`_namedtuple_sub_flags` writes both an index sub-flag and a name sub-flag under the field
*name*, the name winning over the index — so `--pt.0 13` is collected as `{'x': 13}` and is
dropped outright when `--pt.x` is also set. Vanilla stores every key as spelled, index and name
alike (`{'0': 13, '1': 42}`, and `{'x': 13, '0': 9}` beside a name flag), and construction
reconciles them. So the merged dicts differ key for key, breaking the
[byte-identical](../../architecture/cli-adapters/parity.md#byte-identical-merged-dicts) rule, and a
user's `--pt.0` silently disappears when a `--pt.x` rides along. The fix direction is to store
the keys as spelled and leave the win to construction, as vanilla does; the "name wins over
index" priority the docstring documents is a collection-time decision vanilla never makes.

Detail added while fixing BUG-61 (closed): the renaming bites under `Optional` too, and there
the two sides refuse differently. On the plain spelling `--pt 1 2 --pt.0 9` gives vanilla
`{'x': 1, 'y': 2, '0': 9}`, which `build()` rejects (`Unknown field(s) ['0']`), while the
adapters' re-keyed `{'x': 9, 'y': 2}` builds `Pt(x=9, y=2)`. Under `Pt | None` — routed through
the union shaper since BUG-61 — the adapters produce `{'pt': {'*': ['1', '2'], 'x': 9}}` against
vanilla's `{'pt': {'*': ['1', '2'], '0': 9}}`: the same `'*'` base on both sides, the index key
renamed on one.

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


argv = ["--pt.x", "13", "--pt.0", "9"]
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
print("vanilla :", confarg.merge(T, argv=argv, env={}))

# expected: the two merged dicts are equal
# actual:
#   argparse: {'pt': {'x': 13}}
#   vanilla : {'pt': {'x': 13, '0': 9}}
```

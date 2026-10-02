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
[byte-identical](../../architecture/04-cli-adapters.md#byte-identical-merged-dicts) rule, and a
user's `--pt.0` silently disappears when a `--pt.x` rides along. The fix direction is to store
the keys as spelled and leave the win to construction, as vanilla does; the "name wins over
index" priority the docstring documents is a collection-time decision vanilla never makes.

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

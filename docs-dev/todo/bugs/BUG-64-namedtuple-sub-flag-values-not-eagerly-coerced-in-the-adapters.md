# BUG-64 — A namedtuple's sub-flag values are not eagerly coerced in any adapter

**Where:** `src/confarg/cli/_collect.py` (`_namedtuple_sub_flags`) · **Filed:** 2026-09-29
**Effort:** S · **Risk:** medium · **Impact:** behavior

Found while fixing BUG-59 (closed)
(same defect, different site, so it is filed beside it rather than folded into that change).

Vanilla coerces each `--<field>.<name>` / `--<field>.<index>` sub-flag value to the namedtuple
field type the path resolves to (the scalar tail of `_consume_typed_arg`). The adapters'
`_namedtuple_sub_flags` stores `_str_token` for every sub-flag unconditionally, so the merged
dict holds strings and only `build()` rescues the types — the same gap BUG-59 closed for the
positional token run, and the same
[byte-identical](../../architecture/04-cli-adapters.md#byte-identical-merged-dicts) break. The
fix direction is the same too: coerce with the per-field type `_namedtuple_fields(core)` names,
per key, instead of tokenizing everything. All four adapters are affected.

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


argv = ["--pt.x", "13", "--pt.y", "42"]
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
print("vanilla :", confarg.merge(T, argv=argv, env={}))

# expected: the two merged dicts are equal
# actual:
#   argparse: {'pt': {'x': '13', 'y': '42'}}
#   vanilla : {'pt': {'x': 13, 'y': 42}}
```

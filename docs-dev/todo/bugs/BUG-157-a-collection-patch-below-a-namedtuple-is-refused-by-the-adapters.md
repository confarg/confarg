---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_is_collection_patch_path
effort: S
risk: high
impact: behavior
---
# BUG-157 — A collection patch below a namedtuple field is refused by the adapters

`_is_collection_patch_path` stops a branch as soon as it stands on a namedtuple, so a list or
dict *inside* a namedtuple field is never a collection patch. The static walk registers the
namedtuple's own fields and indices, but no static walk can list `--pair.items.0`, and with the
argv scan declining it too, argparse, click, typer and cyclopts all refuse the flag at parse
time while vanilla writes it. Fix direction: let the namedtuple stop only its own segment
(drop `NAMEDTUPLE` from the stopping `case`), so a branch walks on into the field and answers
yes at the collection below. See
[collection patch parity](../../architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity)
and [one walk, many questions](../../architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions).

```python
from dataclasses import dataclass, field
from typing import NamedTuple

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


class Pair(NamedTuple):
    name: str
    items: list[int]


@dataclass
class Cfg:
    pair: Pair = field(default_factory=lambda: Pair("a", [1, 2]))


argv = ["--pair.items.0", "5"]
print("vanilla :", confarg.merge(Cfg, argv=argv, env={}, config_flag=""))
try:
    parser = make_parser(Cfg, argv=argv, config_flag="")
    print("argparse:", merge_namespace(Cfg, parser.parse_args(argv), argv=argv, config_flag=""))
except SystemExit:
    print("argparse: parse-time rejection")

# expected: argparse merges what vanilla merges
# actual:
#   vanilla : {'pair': {'items': {'0': 5}}}
#   argparse: parse-time rejection
# click, typer and cyclopts refuse it the same way ("No such option" / "Unknown option").
```

# BUG-80 — A namedtuple's negative index sub-flags are unreachable on the adapters

**Where:** `src/confarg/cli/_build.py` (`_collect_namedtuple_specs`) · **Filed:** 2026-09-30
**Effort:** S · **Risk:** medium · **Impact:** behavior

Found while fixing BUG-65 (closed). Registration builds a namedtuple's per-index flags from
`enumerate(fields)`, so only the non-negative spellings exist — but the vanilla parser accepts
`--pt.-1` and stores it as spelled (`{'pt': {'-1': 9}}`), leaving `build()` to refuse it with
`index -1 out of range`. The four adapters never register the flag, so each refuses at parse
time in its own framework's voice (`unrecognized arguments` on argparse, its own usage error on
click, typer and cyclopts), and their merged dict can never equal vanilla's for this spelling —
the [byte-identical](../../architecture/cli-adapters/parity.md#byte-identical-merged-dicts)
rule again. `_construct_namedtuple` even has a branch for negative index keys
(`k.startswith("-")`), dead in practice because `idx < 0` always refuses.

The fix direction is a maintainer's choice between the two parities: register the negative
spellings (collection stores them, `build()` refuses, matching vanilla), or make vanilla's type
walk refuse a negative segment on a fixed-length sequence so all five agree at parse time. The
second reading has precedent on its side: a namedtuple has no `-1` position to name, while
`--items.-1` is meaningful on the varlen collection that supports it
(`tests/cli/test_backend_contract.py`, the `--input.-1` contract test).

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


argv = ["--pt.-1", "9"]
print("vanilla :", confarg.merge(T, argv=argv, env={}))
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))

# expected: the two merged dicts are equal
# actual:
#   vanilla : {'pt': {'-1': 9}}
#   argparse: SystemExit(2) — "unrecognized arguments: --pt.-1 9"
#   click/typer/cyclopts: their own parse-time usage errors, all observed
```

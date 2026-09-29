# BUG-68 — A sub-flag more than one level below a namedtuple field is accepted only by vanilla

**Where:** `src/confarg/cli/_build.py` (static flag walk) · `src/confarg/cli/_collect.py`
(`_namedtuple_sub_flags`) · **Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

Found while fixing BUG-66 (closed); the arity-plus-sub-flag merge was settled for the one level
the adapters collect, and the level below it turned out not to exist there.

Vanilla resolves any path through a namedtuple's fields, so `--pt.inner.a 5` on a namedtuple
whose field `inner` is itself a struct (or another namedtuple) descends twice and stores
`{'pt': {'inner': {'a': 5}}}`. The adapters register and collect a namedtuple's sub-flags one
level deep (`_namedtuple_sub_flags` looks at `--<flag>.<name>` and `--<flag>.<index>` only), and
the dynamic registration scan does not add the deeper path, so all four reject the flag the
host framework's own way — argparse, click and typer exit with their usage error, cyclopts prints
`Unknown option: --pt.inner.a. Did you mean --pt.inner?`. Not an approved divergence
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)).

The fix direction: the static walk should recurse into a namedtuple's struct-shaped fields (as
it already recurses into a struct's), and `_collect_ns_namedtuple` should hand those deeper
paths to the struct collection instead of collecting one level of sub-flags — the same
priority (sub-flag over arity position) applies at the deeper level.

```python
from dataclasses import dataclass
from typing import NamedTuple, Optional

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


class Inner(NamedTuple):
    a: int = 0


class Point(NamedTuple):
    inner: Optional[Inner] = None


@dataclass
class T:
    pt: Point = Point()


argv = ["--pt.inner.a", "5"]
parser = make_parser(T, argv=argv)
print("vanilla :", confarg.merge(T, argv=argv, env={}))

# expected: argparse prints the same dict vanilla does, {'pt': {'inner': {'a': 5}}}
# actual:
#   vanilla : {'pt': {'inner': {'a': 5}}}
#   argparse: usage error, "unrecognized arguments: --pt.inner.a 5" (merge_namespace
#             never runs; click, typer and cyclopts reject it likewise)
```

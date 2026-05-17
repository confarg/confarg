# BUG-25 — An escaped `_bind` beside a plain opener is vanilla-only

**Where:** `src/confarg/cli/_build.py` (`_escaped_opener_specs`) · **Filed:** 2026-09-15
**Effort:** S · **Risk:** high · **Impact:** config

Dynamic registration adds escaped flags only for the escaped *openers* actually typed, so a
`--<field>._bind.<param>` next to a *plain* opener is never registered and all three
adapters reject the flag outright. Vanilla accepts it and stores `_bind` as ordinary data —
the documented reading, since the opener's form alone selects the mode
([06-callables.md#plain-and-escaped-directives](../../architecture/06-callables.md#plain-and-escaped-directives)).
Neither half is obviously right: the pair is very likely a user who meant `--<field>.bind`,
so the fix may be to register it and let construction raise on the stray kwarg, or to
reject it in vanilla too. Pre-existing, and the bare-string shorthand behaves exactly like
the explicit opener shown here; found while fixing BUG-23.

```python
import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import confarg
from confarg.cli.argparse import merge_namespace, populate_parser


def shout(name: str, punct: str = ".") -> str:
    return f"{name.upper()}{punct}"


@dataclass
class Config:
    fn: Callable[..., Any] = str.upper


argv = ["--fn.fn", "__main__.shout", "--fn._bind.punct", "!"]
print("vanilla: ", confarg.merge(Config, argv=argv, env={}))
parser = argparse.ArgumentParser()
populate_parser(Config, parser, argv=argv)
print("argparse:", merge_namespace(Config, parser.parse_args(argv), argv=argv, env={}))
# expected: both front-ends agree, whichever way the pair is settled
# actual:   vanilla:  {'fn': {'fn': '__main__.shout', '_bind': {'punct': '!'}}}
#           argparse: error: unrecognized arguments: --fn._bind.punct !
#                     SystemExit: 2
```

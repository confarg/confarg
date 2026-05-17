# BUG-28 — A callable's sibling kwarg the signature does not name is vanilla-only

**Where:** `src/confarg/cli/_build.py` (`_collect_callable_field_specs`) · **Filed:** 2026-09-16
**Effort:** S · **Risk:** medium · **Impact:** config

Sibling kwargs of a `Callable` field are registered only from the named target's signature,
so a `--<field>.<name>` the signature does not carry is rejected by all three adapters while
vanilla merges it and lets construction judge it. Two shapes reach it: a scalar spelled with
the bind word the opener left inactive (`--fn._bind 5`, ordinary data per
[06-callables.md#plain-and-escaped-directives](../../architecture/06-callables.md#plain-and-escaped-directives)),
and any sibling kwarg typed with no opener anywhere, which names no target to inspect. The
*subkey* form of both was fixed in BUG-25 by registering from the path
([04-cli-adapters.md#static-and-dynamic-flags](../../architecture/04-cli-adapters.md#static-and-dynamic-flags));
the scalar form was left out because the adapters' flat collector reads a sibling scalar only
when an opener is present, so registering it alone would drop the value silently instead —
the collector has to learn the no-opener case in the same change. Both halves error either
way today, so the gap is in *which* error, not in whether one is raised. Found while fixing
BUG-25.

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


for argv in (["--fn.fn", "__main__.shout", "--fn._bind", "5"], ["--fn.greeting", "Hi"]):
    print("ARGV", argv)
    print("  vanilla:", confarg.merge(Config, argv=argv, env={}))
    parser = argparse.ArgumentParser()
    populate_parser(Config, parser, argv=argv)
    try:
        print("  argparse:", merge_namespace(Config, parser.parse_args(argv), argv=argv, env={}))
    except SystemExit as e:
        print("  argparse: SystemExit", e)
# expected: both front-ends agree — the adapter accepts the flag and construction rejects the kwarg
# actual:   ARGV ['--fn.fn', '__main__.shout', '--fn._bind', '5']
#             vanilla: {'fn': {'fn': '__main__.shout', '_bind': '5'}}
#             argparse: SystemExit 2   (error: unrecognized arguments: --fn._bind 5)
#           ARGV ['--fn.greeting', 'Hi']
#             vanilla: {'fn': {'greeting': 'Hi'}}
#             argparse: SystemExit 2   (error: unrecognized arguments: --fn.greeting Hi)
```

# BUG-75 — Argparse alone refuses the tokens that complete a `=`-spelled fixed-arity run

**Where:** `src/confarg/cli/argparse/_register.py` (`nargs="*"`) · **Filed:** 2026-09-29
**Effort:** S · **Risk:** medium · **Impact:** behavior

Vanilla treats the value half of `--pair=1` as the first positional of its occurrence's run
and consumes what follows, and the cyclopts, click and typer adapters read the same run back
off argv
([04-cli-adapters.md#whole-value-flags](../../architecture/04-cli-adapters.md#whole-value-flags)),
so `--pair=1 2` is `{'pair': [1, 2]}` on four of the five front-ends. Argparse's own parser
is the exception: `--pair=1` binds one token to the flag and leaves `2` a stray positional
with no destination, so it exits with its own usage error instead of the value every other
front-end builds. A fixed-arity flag is registered `nargs="*"` there, so confarg's guard
never sees the run either — argparse simply has no spelling for "continue my `=` run on the
next token".

The fix direction is a maintainer decision: either record the refusal as an approved
divergence narrowed to argparse, or make vanilla refuse `--pair=1 2` so all five front-ends
agree on a refusal.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair=1", "2"]
print("vanilla :", confarg.merge(T, argv=argv, env={}))
parser = make_parser(T, argv=argv)
try:
    print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
except SystemExit:
    print("argparse: SystemExit 2 (usage error: unrecognized arguments: 2)")

# expected: one verdict for both
# actual:
#   vanilla : {'pair': [1, 2]}
#   argparse: SystemExit 2 (usage error: unrecognized arguments: 2)
```

# BUG-73 — An earlier short occurrence of a fixed-arity flag vanishes on the greedy adapters

**Where:** `src/confarg/cli/_collect.py` (`_require_fixed_arity`) · **Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

Vanilla refuses an incomplete occurrence the moment it meets one: `_consume_fixed_tuple_args`
demands its tokens before the next flag arrives, so `--pair 1 --pair 3 4` is `Missing value for
'--pair'`. Click and typer refuse it too, through their exact-count parsers. Argparse registers
the flag `nargs="*"`
([04-cli-adapters.md#whole-value-flags](../../architecture/04-cli-adapters.md#whole-value-flags)),
so the first occurrence consumes its short run, the plain store overwrites it with the second,
and `_require_fixed_arity` only ever sees the surviving run — both bounds are answered per
list, not per occurrence. The BUG-62 fix made cyclopts match its argparse peer here (the
`_last_occurrence_convert` converter keeps the last run only), so the silent acceptance now
spans both greedy front-ends. The bare spelling vanishes the same way on argparse
(`--pair --pair 3 4` is also `{'pair': [3, 4]}`); on cyclopts it asserts instead — that crash
is [BUG-74](BUG-74-cyclopts-asserts-on-a-bare-fixed-arity-occurrence-beside-a-valued-one.md).

The fix direction is an argv read-back of every occurrence's run — the read-back
`_arity_flag_writes_last` already performs — or a maintainer decision that the greedy
front-ends' acceptance is the approved shape, recorded in
[10-design-decisions.md](../../architecture/10-design-decisions.md).

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "1", "--pair", "3", "4"]
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
try:
    print("vanilla :", confarg.merge(T, argv=argv, env={}))
except Exception as e:
    print("vanilla :", type(e).__name__ + ":", e)

# expected: both refuse the first occurrence's short run (Missing value for '--pair')
# actual:
#   argparse: {'pair': [3, 4]}
#   vanilla : ConfargError: Missing value for '--pair'. Usage: --pair <value>
```

# BUG-62 — Cyclopts accumulates a repeated fixed-arity flag instead of letting the last one win

**Where:** `src/confarg/cli/cyclopts/_register.py` (`consume_multiple=True`) · **Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

A fixed-arity flag *replaces* on a second occurrence: vanilla's `_consume_fixed_tuple_args`
`_set_nested`s the new tokens over the old, and argparse, click and typer all overwrite too, so
`--pair 1 2 --pair 3 4` is `(3, 4)` in four front-ends. Cyclopts registers such a flag
`consume_multiple=True` to buy the whole-value token
([04-cli-adapters.md#whole-value-flags](../../architecture/04-cli-adapters.md#whole-value-flags)),
and that setting also accumulates *across occurrences*, so the collector is handed
`['1', '2', '3', '4']` — one token run that never existed in argv.

Before BUG-60 (closed) the over-long list reached `build()` and failed there; now
`_require_fixed_arity` reports `'3'` as a surplus positional, which is the right rule read
against the wrong input. The defect is the accumulation, not the guard: the collector cannot
tell a four-token run from two two-token runs, so the fix belongs where the tokens are
gathered — cyclopts must keep only the last occurrence for a `_fixed_seq_types` field, the way
its `nargs="*"` argparse peer does by construction.

A varlen list is the opposite and is already right: vanilla *extends* `list[str]` across
occurrences, so accumulating is what parity asks for there. Only the fixed-arity registration
is affected.

```python
from dataclasses import dataclass

import cyclopts

import confarg
from confarg.cli.cyclopts import merge_app, populate_app


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "1", "2", "--pair", "3", "4"]
app = cyclopts.App(name="demo")
populate_app(T, app, argv=argv)
try:
    print("cyclopts:", merge_app(T, app, argv=argv, env={}))
except Exception as e:
    print("cyclopts:", type(e).__name__ + ":", e)
print("vanilla :", confarg.merge(T, argv=argv, env={}))

# expected: both print {'pair': [3, 4]} (argparse, click and typer already do).
# actual:
#   cyclopts: UnknownArgumentError: Unexpected positional argument: '3'. All arguments must be named flags (e.g. --fieldname value).
#   vanilla : {'pair': [3, 4]}

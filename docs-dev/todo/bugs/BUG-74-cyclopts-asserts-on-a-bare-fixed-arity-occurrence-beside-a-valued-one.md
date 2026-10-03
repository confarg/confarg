# BUG-74 — Cyclopts asserts on a bare fixed-arity occurrence beside a valued one

**Where:** `src/confarg/cli/cyclopts/_context.py` (`drop_bare_occurrences`) · **Filed:** 2026-09-29
**Effort:** S · **Risk:** low · **Impact:** behavior

A bare `--pair` on a fixed-arity field is `Missing value`, in vanilla and on the adapters
(BUG-58, closed) — a fixed arity is not one of the shapes a bare flag is reserved for. Alone,
cyclopts still reaches that error: `consume_multiple` reads the bare occurrence as an implicit
empty container, the guard sees `[]` and raises. But a bare occurrence *beside a valued one*
asserts inside cyclopts first, with no message of its own: the implicit empty container meets a
real token, the same framework assertion
[04-cli-adapters.md#a-flag-that-stands-bare](../../architecture/04-cli-adapters.md#a-flag-that-stands-bare)
describes for the flags that do stand bare. A whole-value flag is not one of them, so
`drop_bare_occurrences` leaves the bare occurrence in the argv cyclopts parses, and nothing
refuses it before cyclopts does. Both orders assert (`--pair --pair 3 4` and
`--pair 1 2 --pair`).

The fix direction is the pre-parse refusal pattern of `--config` (BUG-51, closed): scan argv
for a bare occurrence of a whole-value flag and raise `ConfargError.missing_value` before
cyclopts parses. Argparse makes the same argv reach the same `Missing value` since BUG-73
closed; only cyclopts still crashes.

```python
from dataclasses import dataclass

import cyclopts

import confarg
from confarg.cli.cyclopts import merge_app, populate_app


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "--pair", "3", "4"]
app = cyclopts.App(name="demo")
populate_app(T, app, argv=argv)
try:
    print("cyclopts:", merge_app(T, app, argv=argv, env={}))
except Exception as e:
    print("cyclopts:", type(e).__name__ + ":", e)
try:
    print("vanilla :", confarg.merge(T, argv=argv, env={}))
except Exception as e:
    print("vanilla :", type(e).__name__ + ":", e)

# expected: both refuse the bare occurrence (Missing value for '--pair')
# actual:
#   cyclopts: AssertionError:
#   vanilla : ConfargError: Missing value for '--pair'. Usage: --pair <value>
```

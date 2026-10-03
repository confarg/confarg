# BUG-78 — Cyclopts refuses a delete flag spelled twice

**Where:** `src/confarg/cli/cyclopts/_register.py` (the `nargs=0` patch-flag
registration) · **Filed:** 2026-09-30
**Effort:** S · **Risk:** low · **Impact:** behavior

A delete flag registers value-less (`FlagSpec(nargs=0)`, built by
`cli/_build._collect_patch_argv_specs`), and a value-less cyclopts parameter rejects a
second occurrence with a usage error — `Parameter --users- specified multiple times.`
— while vanilla, argparse, click and typer all take it: a delete repeated is the same
delete, and the whole-field one is idempotent anyway. Plain flags repeat fine
(`consume_multiple`, BUG-37) and so do appends (`nargs="*"`); only the value-less family
refuses. Same for a repeated dict-key delete (`--data.a- --data.a-`).

Fix direction: either register the value-less flag so cyclopts accepts repetition, or
drop the surplus occurrences from the argv cyclopts parses — the delete's value never
reaches a parse result the collector reads, since the patch scan reads argv directly, so
the `drop_bare_occurrences` precedent
([cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare))
is the shape. Found while probing the BUG-76 neighborhood.

```python
from dataclasses import dataclass, field

import cyclopts

import confarg
from confarg.cli.cyclopts import merge_app, populate_app


@dataclass
class Config:
    users: list[str] = field(default_factory=list)


argv = ["--users", "a", "--users-", "--users-", "--users", "b"]
app = cyclopts.App(name="demo")
populate_app(Config, app, argv=argv)
try:
    print("cyclopts:", merge_app(Config, app, argv=argv, env={}))
except SystemExit as e:
    print("cyclopts: SystemExit", e)
print("vanilla :", confarg.merge(Config, argv=argv, env={}))

# expected: both {'users': ['b']} — a delete repeated is the same delete, and
#           the occurrence after it starts the new list (BUG-76, closed)
# actual:
#   cyclopts: SystemExit 1   (stderr: "Parameter --users- specified multiple times.")
#   vanilla : {'users': ['b']}
```

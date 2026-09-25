# BUG-35 — A mixed append (`--f+ v` and a bare `--f+`) is rejected by three front-ends

**Where:** `src/confarg/cli/_build.py` · **Filed:** 2026-09-19
**Effort:** M · **Risk:** low · **Impact:** behavior

Left over from BUG-33. An append flag takes zero or more items, and no clicklike option can
be both shapes at once, so the spec follows argv: value-less when no occurrence carries an
item, multi-token otherwise
([04-cli-adapters.md#a-bare-append](../../architecture/04-cli-adapters.md#a-bare-append)).
One argv that spells it *both* ways therefore has to pick one, and the bare occurrence loses:
click and typer report `Option '--users+' requires an argument.`, cyclopts
`Parameter --users+ specified multiple times.`  Vanilla and argparse take it, so it is an
unapproved parity gap
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).

The bare occurrence is a no-op, so nothing is lost by honoring it; the fix has to make the
framework skip it without the registered option claiming the next token. A direction: keep
the multi-token registration and drop the redundant bare occurrences from the argv the
framework parses — which the adapters do not own today, the host application calling its own
command.

```python
from dataclasses import dataclass, field

import click

from confarg.cli.click import from_context, populate_command


@dataclass
class Config:
    users: list[str] = field(default_factory=list)


ARGV = ["--users", "john", "--users+", "billy", "--users+"]


@click.command()
def main(**_kwargs: object) -> None:
    print(from_context(Config, click.get_current_context(), argv=ARGV, env={}, env_prefix=None))


populate_command(Config, main, argv=ARGV)
main(ARGV, standalone_mode=False)
# expected: Config(users=['john', 'billy'])   # confarg.load(Config, argv=ARGV, env={}, env_prefix=None) prints this
# actual:   click.exceptions.BadOptionUsage: Option '--users+' requires an argument.
```

Typer fails identically. cyclopts fails differently, and fails on two bare appends
(`--users+ --users+`) as well, where click, typer, argparse and vanilla all succeed:

```
Parameter --users+ specified multiple times.
```

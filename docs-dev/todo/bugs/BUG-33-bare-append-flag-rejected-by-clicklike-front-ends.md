# BUG-33 — A bare append flag is rejected by the clicklike front-ends

**Where:** `src/confarg/cli/_clicklike/_options.py`, `src/confarg/cli/_build.py` · **Filed:** 2026-09-19
**Effort:** M · **Risk:** low · **Impact:** behavior

`--<list>+` with no value is a no-op append: vanilla, argparse and cyclopts all accept it and
leave the list as the lower-priority sources left it. click and typer reject it with
`Option '--input+' requires an argument.` — an unapproved parity gap
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).

The cause is the one that already forces the fixed-arity divergence
([04-cli-adapters.md#whole-value-flags](../../architecture/04-cli-adapters.md#whole-value-flags)):
`_build` gives an append flag `nargs="*"`, and neither clicklike framework can express
zero-or-more tokens on an option, so `option_kwargs` maps `"*"` to `multiple=True`, which always
demands a value. A fix direction: let the *append* spec carry its own shape, since an append
with no items is meaningful in a way a bare `--tags` is not — or decide the spelling is one
click cannot have and approve the divergence, in which case the four
`examples/16_appending_items/README.md` blocks that claim otherwise have to say so.

This predates the typer front-end: the click half fails identically on the revision before
typer existed. Typer inherits it along with the option class it forked
([04-cli-adapters.md#the-clicklike-seam](../../architecture/04-cli-adapters.md#the-clicklike-seam)),
so the example block added for typer fails the same way the click one already did.

`examples/16_appending_items/README.md` documents the working output for all five front-ends,
so its click and typer `console` blocks are red until this is settled.

```python
from dataclasses import dataclass, field

import click

from confarg.cli.click import from_context, populate_command


@dataclass
class Config:
    input: list[int] = field(default_factory=list)


ARGV = ["--input+"]
ENV = {"MYAPP_INPUT": "[1, 2]"}


@click.command()
def main(**_kwargs: object) -> None:
    print(from_context(Config, click.get_current_context(), argv=ARGV, env=ENV, env_prefix="MYAPP_"))


populate_command(Config, main, argv=ARGV)
main(ARGV, standalone_mode=False)
# expected: Config(input=[1, 2])   # confarg.load(Config, argv=ARGV, env=ENV, env_prefix="MYAPP_") prints this
# actual:   click.exceptions.BadOptionUsage: Option '--input+' requires an argument.
```

Swapping the two imports for `confarg.cli.typer` and driving a one-command `typer.Typer` app
reproduces it identically.

# BUG-38 — A bare `--<list>` clears the list everywhere except click and typer

**Where:** `src/confarg/cli/_build.py` (`_append_carries_items`, `_collect_patch_argv_specs`) · **Filed:** 2026-09-21
**Effort:** S · **Risk:** low · **Impact:** behavior

`--users` with nothing after it empties the list in vanilla, argparse and cyclopts — a varlen
collection consumes greedily and is content with zero tokens — while click and typer answer
`Option '--users' requires an argument.` It is the same shape problem BUG-33 solved one flag
family over: no clicklike option can be both value-less and multi-token, so the spec has to
follow argv ([04-cli-adapters.md#a-bare-append](../../architecture/04-cli-adapters.md#a-bare-append)).
Vanilla, argparse and cyclopts take it, so it is an unapproved parity gap
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).
That section's claim that an append is "the *only* flag family that stands bare" is wrong as
written, and this ticket is why.

Fix: `_append_carries_items` already answers "does any occurrence of this flag in argv carry an
item?", and its precondition holds for **every** varlen collection flag, not only for an append.
Lift it to a neutral `_flag_carries_items` and ask it wherever a varlen spec is built, so a flag
argv never gives an item registers `nargs=0` exactly as a bare `--users+` does — one rule applied
wherever it holds rather than a second special case
([09-invariants.md#delegate-to-the-canonical-function](../../architecture/09-invariants.md#delegate-to-the-canonical-function)).
It asks with `_parse_cli._looks_like_flag`, so the frameworks keep consuming exactly the tokens
vanilla consumes and the dashed-value escape (`--users=--a`, `--users -8`) is unaffected
([10-design-decisions.md#the--form-is-the-escape-for-a-dashed-value](../../architecture/10-design-decisions.md#the--form-is-the-escape-for-a-dashed-value)).

```python
from dataclasses import dataclass, field

import click

from confarg.cli.click import from_context, populate_command


@dataclass
class Config:
    users: list[str] = field(default_factory=list)


ARGV = ["--users"]


@click.command()
def main(**_kwargs: object) -> None:
    print(from_context(Config, click.get_current_context(), argv=ARGV, env={}, env_prefix=None))


populate_command(Config, main, argv=ARGV)
main(ARGV, standalone_mode=False)
# expected: Config(users=[])   # confarg.load(Config, argv=ARGV, env={}, env_prefix=None) prints this
# actual:   click.exceptions.BadOptionUsage: Option '--users' requires an argument.
```

Typer fails identically. With a lower-priority source to clear the divergence is louder still:
over a config file holding `users: ['alice', 'bob']`, vanilla, argparse and cyclopts print
`Config(users=[])` while click and typer refuse the command line.

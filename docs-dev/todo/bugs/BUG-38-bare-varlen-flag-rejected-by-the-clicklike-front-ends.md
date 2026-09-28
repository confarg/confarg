# BUG-38 — A bare `--<list>` clears the list everywhere except click and typer

**Where:** `src/confarg/cli/_build.py` (`_collect_patch_argv_specs`, `_build_leaf_spec`) · **Filed:** 2026-09-21
**Effort:** S · **Risk:** low · **Impact:** behavior

`--users` with nothing after it empties the list in vanilla, argparse and cyclopts — a varlen
collection consumes greedily and is content with zero tokens — while click and typer answer
`Option '--users' requires an argument.` It is the same shape problem BUG-33 and BUG-35 solved
one flag family over: no clicklike option can be both value-less and multi-token
([04-cli-adapters.md#a-bare-append](../../architecture/04-cli-adapters.md#a-bare-append)).
Vanilla, argparse and cyclopts take it, so it is an unapproved parity gap
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).

Fix: the append flag already solves this, and its rule is neutral. A spec marked
`FlagSpec.stands_bare` keeps its multi-token shape and has its bare occurrences dropped from the
argv the framework parses (`cli._argv.drop_bare_occurrences`), so the flag is legal with zero
items on every front-end. The precondition — "vanilla consumes greedily and is content with no
token" — holds for **every** varlen collection flag, not only for an append, so setting
`stands_bare` wherever a varlen spec is built applies one rule where it holds rather than adding
a second special case
([09-invariants.md#delegate-to-the-canonical-function](../../architecture/09-invariants.md#delegate-to-the-canonical-function)).
Unlike an append, a bare `--users` is not a no-op — it *clears* the list — so check that
dropping the token still leaves the vanilla patch scan to record the clear before relying on it.
The filter asks with `_parse_cli._looks_like_flag`, so the frameworks keep consuming exactly the
tokens vanilla consumes and the dashed-value escape (`--users=--a`, `--users -8`) is unaffected
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

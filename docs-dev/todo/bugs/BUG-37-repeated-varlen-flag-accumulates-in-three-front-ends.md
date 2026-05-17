# BUG-37 — A repeated varlen flag accumulates in three front-ends and last-wins in two

**Where:** `src/confarg/_parse_cli.py` · `src/confarg/cli/argparse/_register.py` · **Filed:** 2026-09-21
**Effort:** M · **Risk:** medium · **Impact:** behavior

`--users x --users y` builds `['x', 'y']` under click, typer and cyclopts and `['y']` under
vanilla and argparse. Both readings are silent, so a user who copies the repeated-flag line
the click and typer tutorials teach (`--input 1 --input 0b10`,
[examples/12](../../../examples/12_collections/README.md)) into a vanilla app loses every value
but the last with no diagnostic. The approved divergence covers only which *spelling* each
framework accepts, never what repetition **means**
([04-cli-adapters.md#list-syntax-divergence](../../architecture/04-cli-adapters.md#list-syntax-divergence)),
so this is an unapproved parity gap
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).

**Decided: accumulate.** Last-wins is unreachable for the clicklike front-ends — taking only the
final occurrence would leave a click user no way to write `['x', 'y']` at all, repetition being
their only multi-token spelling — so `--f x --f y` must become a second spelling of `--f x y`
everywhere. Two halves: vanilla's varlen branch extends a list already stored at the path instead
of overwriting it, and the argparse adapter registers `action="extend"` beside `nargs="*"` so the
Namespace carries every occurrence rather than the last.

Out of scope: `--f+` already extends and is untouched, and a **fixed-arity** flag
(`tuple[X, Y]`, namedtuple) is not varlen — `--size 32 32` reads identically in all five
front-ends and repeating the whole flag is already last-wins everywhere
([10-design-decisions.md#a-namedtuple-is-a-fixed-length-sequence](../../architecture/10-design-decisions.md#a-namedtuple-is-a-fixed-length-sequence)).
The rationale for the `+` suffix this sits beside is
[10-design-decisions.md#the--suffix-is-a-merge-operator-not-a-list-spelling](../../architecture/10-design-decisions.md#the--suffix-is-a-merge-operator-not-a-list-spelling).

```python
from dataclasses import dataclass, field

import click

import confarg
from confarg.cli.click import from_context, populate_command


@dataclass
class Config:
    users: list[str] = field(default_factory=list)


ARGV = ["--users", "x", "--users", "y"]

print(confarg.load(Config, argv=ARGV, env={}, env_prefix=None))
# actual: Config(users=['y'])


@click.command()
def main(**_kwargs: object) -> None:
    print(from_context(Config, click.get_current_context(), argv=ARGV, env={}, env_prefix=None))


populate_command(Config, main, argv=ARGV)
main(ARGV, standalone_mode=False)
# actual: Config(users=['x', 'y'])
```

expected: both print `Config(users=['x', 'y'])`, the reading three of the five front-ends
already have.
actual: vanilla and argparse keep only `'y'`.

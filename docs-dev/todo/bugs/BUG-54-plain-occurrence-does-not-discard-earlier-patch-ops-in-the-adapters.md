# BUG-54 — A plain collection flag does not discard the patch ops before it in the adapters

**Where:** `src/confarg/cli/_collect.py` (`_merge_from_flat`) · **Filed:** 2026-09-28
**Effort:** M · **Risk:** medium · **Impact:** config

In vanilla a plain `--<list>` occurrence replaces the whole list, so it discards the patch ops
recorded before it — which is what makes `--tags --tags+ x` a reset followed by an append
([cli-parsing/collection-patches.md#collection-patch-operations](../../architecture/cli-parsing/collection-patches.md#collection-patch-operations)). All four adapters
keep those earlier ops instead: they collect the plain occurrence's value with the flat collector
and then deep-merge the whole patch scan over it, and the scan carries no argv position, so an
append or an index delete standing *before* the flag survives it
([cli-adapters/collection-patch-parity.md#a-patch-op-joins-the-values-the-framework-collected](../../architecture/cli-adapters/collection-patch-parity.md#a-patch-op-joins-the-values-the-framework-collected)).
An unapproved parity gap
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)).

It is the same missing information as [BUG-53](BUG-53-whole-field-delete-beats-a-later-flag-in-the-adapters.md)
— the patch ops reach the merge with no argv order — seen from the other side: there a delete
*before* a set wrongly wins, here an append *before* a plain occurrence wrongly survives. One fix
that gives `_collect_cli_patch_ops` the position of each op relative to the plain occurrences
settles both, so size them together and expect them to land together.

An index delete shows it too, and louder, because the value is silently wrong rather than merely
larger: over a config file holding `tags: [alice, bob]`, `--tags.0- --tags y` prints
`Config(tags=['y'])` in vanilla and `Config(tags=[])` in all four adapters.

```python
from dataclasses import dataclass, field

import click

import confarg
from confarg.cli.click import from_context, populate_command


@dataclass
class Config:
    tags: list[str] = field(default_factory=list)


ARGV = ["--tags+", "x", "--tags", "y"]


@click.command()
def main(**_kwargs: object) -> None:
    print("click:  ", from_context(Config, click.get_current_context(), argv=ARGV, env={}, env_prefix=None))


print("vanilla:", confarg.load(Config, argv=ARGV, env={}, env_prefix=None))
populate_command(Config, main, argv=ARGV)
main(ARGV, standalone_mode=False)
# expected: both print Config(tags=['y']) — the plain occurrence resets the append before it
# actual:   vanilla: Config(tags=['y'])
#           click:   Config(tags=['y', 'x'])
```

argparse, typer and cyclopts print the same `['y', 'x']` as click.

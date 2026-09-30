# BUG-76 — A whole-field delete does not end the adapters' token accumulation

**Where:** `src/confarg/cli/_collect.py` (`_collect_ns_fields`), `src/confarg/_parse_cli.py` (`_handle_delete_token`) · **Filed:** 2026-09-30
**Effort:** M · **Risk:** medium · **Impact:** config

A whole-field delete ends the list being built: vanilla's `_handle_delete_token` pops the
token accumulation at the path, so `--users y --users- --users b` is `['b']` — the occurrence
after the delete starts a new list rather than extending the one the delete discarded
([cli-parsing/collection-patches.md#collection-patch-operations](../../architecture/cli-parsing/collection-patches.md#collection-patch-operations)).
The adapters read the whole value out of the framework's parse result, which has accumulated
every plain occurrence (the repeated-flag convention), so the token of the occurrence before
the delete survives *inside* the value of the one after it. Found while verifying the
BUG-53/BUG-54 fix, which settled which ops a plain occurrence supersedes
([cli-adapters/collection-patch-parity.md#a-plain-occurrence-erases-the-ops-before-it](../../architecture/cli-adapters/collection-patch-parity.md#a-plain-occurrence-erases-the-ops-before-it))
— this is the same argv order seen from a third side, and it cannot be settled by an op's
position alone, because the flat value itself spans the delete.

Fix direction: the patch scan already walks argv in order, so it can hand the collector the
argv position of the last whole-field delete at a path, and the collector can read the plain
occurrences' token runs off argv — `_fixed_arity_occurrence_runs` is the precedent for a
reader of that shape — keeping only the runs that follow the delete, and only for a field
whose flat value came from more than one plain occurrence.

```python
from dataclasses import dataclass, field

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Config:
    users: list[str] = field(default_factory=list)


ARGV = ["--users", "y", "--users-", "--users", "b"]

print("vanilla :", confarg.merge(Config, argv=ARGV, env={}))
parser = make_parser(Config, argv=ARGV)
print("argparse:", merge_namespace(Config, parser.parse_args(ARGV), argv=ARGV, env={}))

# expected: both print {'users': ['b']}
# actual:   vanilla : {'users': ['b']}
#           argparse: {'users': ['y', 'b']}
```

click, typer and cyclopts print the same `['y', 'b']` as argparse.

# BUG-53 — a whole-field delete wins over a later flag in the adapters, not in vanilla

**Where:** `src/confarg/cli/_collect.py` (`_restore_patch_deletes`) · **Filed:** 2026-09-28
**Effort:** M · **Risk:** medium · **Impact:** config

`--items- --items a` is `['a']` under vanilla and `[]` under argparse, click, typer and cyclopts.
Vanilla honors argv order — the delete drops the field, the flag that follows sets it again — while
the adapters re-assert every delete *after* the merge, so a delete anywhere in argv beats a value
anywhere in argv
([cli-adapters/collection-patch-parity.md#a-patch-op-joins-the-values-the-framework-collected](../../architecture/cli-adapters/collection-patch-parity.md#a-patch-op-joins-the-values-the-framework-collected)).

Re-assertion is deliberate and needed: `_deep_merge` applies a delete on sight, which is wrong
inside one channel where the sentinel is a record for `_merge_sources` to apply. The sanction for
letting it win is the argv-order convention "whole value first, refinements after" — but
delete-then-set *is* that useful order, and it is the order someone reaches for to clear a
configured list and put something else in its place. So the gap is unapproved
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)).

`--items-` and a bare `--items` are both accepted by every front-end, and it is the *delete*
spelling whose follow-up flag is silently dropped — which is what makes this worth fixing rather
than documenting. A fix has to give
`_restore_patch_deletes` the argv position of each delete, so a sibling set *after* it survives and
one *before* it does not.

[BUG-54](BUG-54-plain-occurrence-does-not-discard-earlier-patch-ops-in-the-adapters.md) is the same
missing argv position seen from the other side — an append *before* a plain occurrence wrongly
survives it — so the two want one fix and should be sized together.

```python
from dataclasses import dataclass, field

import confarg
from confarg.cli.argparse import from_namespace, make_parser


@dataclass
class Config:
    items: list[str] = field(default_factory=list)


ARGV = ["--items-", "--items", "a"]

print(confarg.load(Config, argv=ARGV, env={}, env_prefix=None))
# vanilla:  Config(items=['a'])

parser = make_parser(Config, argv=ARGV)
print(from_namespace(Config, parser.parse_args(ARGV), argv=ARGV, env={}, env_prefix=None))
# argparse: Config(items=[])
```

expected: both print `Config(items=['a'])` — the delete drops the configured list, the flag after it
supplies a new one.
actual: only vanilla does; argparse prints `Config(items=[])`, and so do click, typer and cyclopts.

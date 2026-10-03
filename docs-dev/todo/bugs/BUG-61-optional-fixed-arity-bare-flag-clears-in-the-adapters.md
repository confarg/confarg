# BUG-61 — A bare optional fixed-arity flag clears in the adapters and raises in vanilla

**Where:** `src/confarg/cli/_collect.py` (`_collect_ns_fields`, the `_unwrap_optional` call)
**Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

`tuple[X, Y] | None` and `NamedTuple | None` are *unions with a sequence variant* to vanilla, so
`_consume_collection_or_scalar` consumes them greedily and `_union_seq_value` rejects an empty
token run: the union has no varlen variant, so `[]` can build nothing and a bare `--pair` is
`Missing value` ([cli-parsing/token-consumption.md#unions-with-sequence-variants](../../architecture/cli-parsing/token-consumption.md#unions-with-sequence-variants)).
`_collect_ns_fields` unwraps `Optional` before dispatching, so the same field reaches the
fixed-arity/namedtuple branch instead and the empty list is stored — the check in
`_collect_union_seq_value` that
[cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)
counts on is never reached. Not an approved divergence
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)).

Only the *bare* spelling diverges for `tuple[X, Y] | None`: `--pair 1` and `--pair 1 2` already
agree, because the adapters store the raw token run and vanilla does too. A *namedtuple* under
`Optional` diverges further (found while fixing BUG-66, closed): vanilla's union branch keeps
the run raw (`--pt 1 2` is `{'pt': ['1', '2']}`), while the adapters' namedtuple branch coerces
it (`{'pt': [1, 2]}`), and the arity-plus-sub-flag merge takes the shapes of
[BUG-66](../../architecture/design-decisions/namedtuple-arity-flag-argv-order.md#a-namedtuples-arity-flag-and-its-sub-flags-merge-in-argv-order)
on one side and the `'*'` list-op shape on the other. Routing the optional field through
`_collect_union_seq_value` settles all of it at once. So the fix is not "require the arity
here" — that would reject `--pair 1`, which vanilla accepts — but routing an optional fixed-arity
field through `_collect_union_seq_value`, the way vanilla routes it through `_union_seq_value`.
Note that the namedtuple sub-flags (`--pair.x`, `--pair.0`) must keep working across that move.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class T:
    pair: tuple[int, int] | None = None


argv = ["--pair"]
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
try:
    print("vanilla :", confarg.merge(T, argv=argv, env={}))
except Exception as e:
    print("vanilla :", type(e).__name__ + ":", e)

# expected: both raise ConfargError: Missing value for '--pair'. Usage: --pair <value>
# actual:
#   argparse: {'pair': []}
#   vanilla : ConfargError: Missing value for '--pair'. Usage: --pair <value>
```

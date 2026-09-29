# BUG-60 — The argparse and cyclopts adapters over-fill a fixed-arity flag

**Where:** `src/confarg/cli/_collect.py` (`_require_fixed_arity`) · **Filed:** 2026-09-29
**Effort:** S · **Risk:** low · **Impact:** behavior

The mirror of [BUG-58](../../architecture/03-cli-parsing.md#token-consumption), which BUG-58's
fix deliberately left alone: `--pair 1 2 3` on a `tuple[int, int]` stops vanilla at the fourth
token (`UnknownArgumentError`, because a value run ends where the arity does), while argparse
and cyclopts register the flag `nargs="*"` and hand over all three. `merge()` therefore returns
a dict from the adapters where vanilla raises. `load()` raises either way, but with a different
diagnosis — `build()`'s arity message instead of the parse-time one — so the divergence is
visible to a user, and it is not an approved one
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).

`--pair '[13]' 9` is the same gap in its whole-value spelling: vanilla takes the lone array and
trips on `9`; the adapters see two tokens, no lone array, and a satisfied arity.

Fix direction: `_require_fixed_arity` already owns the "does this token run fill the flag?"
question and is the natural place for the upper bound. What it cannot reproduce is vanilla's
*message*, which names the first token past the arity rather than the flag —
`TestFixedSequenceContract.test_tuple_too_many_tokens_raises` currently passes only because both
sides raise *some* `ConfargError`, so tightening it is part of the work.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "1", "2", "3"]
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
try:
    print("vanilla :", confarg.merge(T, argv=argv, env={}))
except Exception as e:
    print("vanilla :", type(e).__name__ + ":", e)

# expected: both raise UnknownArgumentError: Unexpected positional argument: '3'.
# actual:
#   argparse: {'pair': ['1', '2', '3']}
#   vanilla : UnknownArgumentError: Unexpected positional argument: '3'. All arguments must be named flags (e.g. --fieldname value).
```

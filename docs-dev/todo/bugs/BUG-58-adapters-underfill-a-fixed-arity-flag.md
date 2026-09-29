# BUG-58 — The argparse and cyclopts adapters still under-fill a fixed-arity flag

**Where:** `src/confarg/cli/_collect.py` (`_collect_ns_fields` leaf branch,
`_collect_ns_namedtuple`) · **Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

BUG-43 fixed the vanilla parser: a
fixed-arity flag short of its arity is `Missing value for '--pair'`, because a fixed arity is not
one of the shapes a bare flag is reserved for
([03-cli-parsing.md#token-consumption](../../architecture/03-cli-parsing.md#token-consumption),
[10-design-decisions.md#a-whole-value-flag-needs-its-value](../../architecture/10-design-decisions.md#a-whole-value-flag-needs-its-value)).
The adapters were not fixed with it and the divergence is not an approved one
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).

`--pair` is registered `nargs="*"` in argparse and cyclopts, so the framework hands over however
many tokens it found and `_collect` stores them unchecked. Click and typer register the exact
token count and so reject the short form themselves — they need no change; the gap is argparse
and cyclopts.

Fix direction: the token list `_collect` receives is what vanilla's `_require_value` loop guards,
so the arity check belongs beside the other shaping `_collect` mirrors — one function taking
`(arity, tokens, flag)`, which is also the seam
[REF-65](../refactors/REF-65-collect-reimplements-the-token-shaping.md) wants to delegate through.
Take care not to re-reject the whole-value spellings: `--pair '[13]'` is a genuine *arity* error
`build()` owns (`TestFixedSequenceContract.test_tuple_too_few_tokens_raises`), not a missing
value, and `_json_array_override` is what tells the two apart.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "1"]
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
try:
    print("vanilla :", confarg.merge(T, argv=argv, env={}))
except Exception as e:
    print("vanilla :", type(e).__name__ + ":", e)

# expected: both raise ConfargError: Missing value for '--pair'. Usage: --pair <value>
# actual:
#   argparse: {'pair': ['1']}
#   vanilla : ConfargError: Missing value for '--pair'. Usage: --pair <value>
```

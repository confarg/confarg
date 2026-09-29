# BUG-59 — A fixed-arity flag's elements are not eagerly coerced in any adapter

**Where:** `src/confarg/cli/_collect.py` (`_coerce_leaf_value`,
`_namedtuple_arity_value`) · **Filed:** 2026-09-29
**Effort:** S · **Risk:** medium · **Impact:** behavior

Vanilla coerces a fixed-length sequence's tokens to their element types as it consumes them
(`_parse_cli._consume_fixed_tuple_args` calls `_try_coerce` per positional type), so
`--pair 1 2` on a `tuple[int, int]` merges `{'pair': [1, 2]}`. The adapters do not:
`_coerce_leaf_value` asks `_elem_type` only when `_is_varlen_collection(core)` holds, which a
fixed tuple fails, so every element stays the `_StrToken` the framework handed over and the
merged dict is `{'pair': ['1', '2']}`.

That breaks the byte-identical rule outright
([04-cli-adapters.md#byte-identical-merged-dicts](../../architecture/04-cli-adapters.md#byte-identical-merged-dicts),
[09-invariants.md](../../architecture/09-invariants.md)) — and the point of coercing eagerly is
that a merged dict carries the same types whichever channel filled it, so a CLI number works
inside an expression ([03-cli-parsing.md#token-consumption](../../architecture/03-cli-parsing.md#token-consumption)).
`build()` coerces the tokens afterwards, which is why the constructed object still comes out
right and no test caught this.

`_fixed_seq_types` is the canonical answer to "how many tokens, of which types?"
([09-invariants.md#delegate-to-the-canonical-function](../../architecture/09-invariants.md#delegate-to-the-canonical-function)),
so the fix is to consult it in `_coerce_leaf_value` beside the varlen branch rather than to add a
second arity walk — the same delegation
[REF-65](../refactors/REF-65-collect-reimplements-the-token-shaping.md) asks for. All four
adapters are affected, click and typer included.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "1", "2"]
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
print("vanilla :", confarg.merge(T, argv=argv, env={}))

# expected: the two merged dicts are equal
# actual:
#   argparse: {'pair': ['1', '2']}
#   vanilla : {'pair': [1, 2]}
```

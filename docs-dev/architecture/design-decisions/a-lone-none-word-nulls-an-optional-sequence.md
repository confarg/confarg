# A lone none word nulls an optional sequence

`--xs none` sets a `list[int] | None` field to `None`, as `APP_XS=none` does.
The same holds for every optional sequence: a set, a variable or fixed tuple, a namedtuple, a union of sequences with `None`.
A none word is read only when it stands alone.
Beside another token (`--xs none 1`, `--xs none --xs 1`) it is an item, and so it is inside an inline array (`--xs '["none"]'`).

The none word is read before the element type is asked, so `list[str] | None` and `list[int | None] | None` take `--xs none` as `None` too, not `['none']` or `[None]` (maintainer-chosen).
The environment already answered `None` there, because the single-variant union reads the none word before the variant sees the value.
Reading the element type first on the CLI only would have been a divergence with no backend idiom behind it ([invariants](../invariants.md#cross-channel-parity)).
The one-item list is still reachable: `--xs '["none"]'`, `--xs.json '["none"]'`, or a file's `xs: [none]`.

**The parser stores the lone token bare, and construction reads it.**
`_union_seq_value`, which shapes every optional sequence's tokens (the CLI dispatches the union, not its unwrapped arm), stores a lone none word as a token rather than a one-item list.
That is the environment's shape, so `merge()` writes `{'xs': 'none'}` on both channels.
`build()` then reads it through the single-variant union as it reads the environment's.
The parser does not decide on its own whether the token is a none word: it asks `_construct._selects_none`, the predicate construction selects `None` with, so the two layers cannot drift.
The parser stores a token, never `None`, so the merge stays unvalidated ([invariants](../invariants.md#merge-stays-unvalidated)).

- Rejected: construction reading a one-token list as `None` under `X | None`.
  The merged dicts would still have differed by channel (`['none']` against `'none'`), and a one-item token list reaching `build()` by another route would have been reinterpreted as `None` too.
- Precedents read the null word off the whole value before shaping a list.
  Hydra's override grammar reads `xs=null` as `None` for any field. pydantic-settings reads the `cli_parse_none_str` string as `None`. jsonargparse parses a flag's value as YAML, so `--xs null` is `None` for an `Optional[List[int]]` *(inferred)*.
- Cost: a bare token cannot put the item `none` alone in an optional `list[str]`.
  It takes the inline array, the JSON cast or a file.
  A non-optional `list[str]` is unaffected, since only a union counting `None` reads the word (BUG-163).

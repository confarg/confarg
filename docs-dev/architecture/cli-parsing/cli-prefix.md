# cli_prefix

`cli_prefix` requires `--<prefix>.` on every flag, so configuration arguments stay
distinguishable from the host application's own — the case the adapters exist for. All four
front-ends support it ([CLI adapters](../cli-adapters/cli-prefix-boundaries.md#the-cli_prefix-boundaries)).

The adapters take it on `populate_*`, which owns flag naming, and **record** it there; the
merge step recovers it, so `merge_*`/`from_*` need not repeat it. Passing one that disagrees
with what was registered raises rather than silently matching no flag — the objection that
once kept the prefix out of the adapters, answered instead of avoided.

Vanilla owns the whole command line, so a flag outside the prefix is an
`UnknownArgumentError`. An adapter does not: there, a flag outside the prefix belongs to the
host framework and is left alone. That is not a divergence in the prefix but the adapter
model itself — it holds with or without one.

A non-struct (scalar) target has no field name to address, so `--<prefix> VALUE` is its only
CLI spelling, handled by `_handle_scalar_root`, on the adapters too. Without a prefix it has no CLI spelling at all, in any front-end.
`--<prefix>.json` reaches the same root through the
[root cast](casts-and-reserved-words.md#force-casts).

A **struct-like** root (dataclass, plain class — a registered leaf included) refuses the bare
flag instead (BUG-91): nothing about `--<prefix> VALUE` names a field, and a value consumed
for the empty path would be silently dropped — the adapters had refused it at parse time all
along, so vanilla's `UnknownArgumentError` is the refusal the five front-ends share. A
registered leaf as the root keeps its flat tagged spelling
(`--<prefix>.class uuid.UUID --<prefix>.hex …`), the one
[a registered leaf is opted back in with](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in).

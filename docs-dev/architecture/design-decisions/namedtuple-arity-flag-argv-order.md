# A namedtuple's arity flag and its sub-flags merge in argv order

`--pt 1 2 --pt.y 9` and `--pt.y 9 --pt 1 2` used to produce three different merged dicts
between the two sides: vanilla promoted the arity list to the list-op shape
(`{'*': [1, 2], 'y': 9}`, unbuildable — `'*'` names no field) or dropped the sub-flag
outright, and the adapters merged the two halves order-independently, so the flag the
user typed last had no effect. The rule chosen: **the latest arguments overwrite the
earlier ones**, per path and in argv order — the same last-write-wins the other
[sub-flag rules](whole-value-then-subkey.md#a-whole-value-followed-by-a-subkey-opens-rather-than-collides) read:

- a sub-flag writes at `pt.y`, so it *refines* what is at `pt`: the arity flag's
  positional list is re-keyed under its field names first, and the sub-flag overrides
  its own position — `{'x': 1, 'y': 9}`;
- the arity flag writes at `pt`, so a later occurrence *replaces* the field wholesale —
  `{'pt': [1, 2]}`, the sub-flag gone, as any later write at a path drops what the path
  held.

Vanilla gets both from its sequential scan plus one promotion:
`_parse_cli._promote_namedtuple_positional` re-keys the positional list by field name
before a sub-flag descends, the namedtuple counterpart of the `'*'` base `_set_nested`
gives a *varlen* collection's index patches — a plain `tuple[int, int]` keeps the `'*'`
shape, which builds there. The adapters' CLI channel is the same sequential scan over the
same argv ([CLI adapters](../cli-adapters/model.md#argv-is-the-only-writer)), so the same argv
produces byte-identical dicts on all five front-ends — interleavings included
(`--pt.x 1 --pt 7 8 --pt.y 2`), which the per-flag argv read-back the adapters first used
(`_arity_flag_writes_last`) could not describe (BUG-111).

The sub-flag's value is eagerly coerced, like every other leaf token. The adapters' former
collector used to store it raw, which put a `str` where vanilla stored the number and made
`--pt.y 9 --double '${pt.y * 2}'` fail on the four adapters (`'9' * 2` is `'99'`)
while vanilla said 18 — the gap PR #99 closed for the other leaves.

The alternatives, and why not:

- **Keep vanilla's `'*'` promotion, make the adapters match.** One rule fewer in the
  parse loop. Rejected because `{'*': [1, 2], 'y': 9}` is a shape `build()` rejects,
  so the fix would have standardized an unbuildable output.
- **Adopt the adapters' order-independent merge** (sub-flags always ride). Rejected: a
  flag the user typed last would vanish — the complaint that filed the bug — and
  vanilla would have to resurrect sub-flags an arity flag had already overwritten.
- **Store the sub-flag's token raw**, as the adapters did. Rejected: the merged dict
  would carry types no other channel produces, and an expression over the field would
  read the text.

The optional spelling keeps the generic promotion on both sides. `Point | None` is a union
with a sequence variant to the vanilla scan, so `_promote_namedtuple_positional` — which asks
the field as resolved — never fires for it: a sub-flag descends through the plain
`_set_nested`, giving the `'*'` list-op base a *varlen* collection's index patches ride on.
The adapters run the same scan
([whole-value flags](../cli-adapters/whole-value-flags.md#whole-value-flags)), so they store
that shape too, and the arity-plus-sub-flag merge that used to build on the adapters
alone (`{'x': 1, 'y': 9}`) now fails in `build()` on all five front-ends identically.
Re-keying the optional spelling by field name as well was rejected: it is not what vanilla
produces, and the plain spelling is the only one whose promotion vanilla performs.

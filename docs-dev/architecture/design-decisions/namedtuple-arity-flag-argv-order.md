# A namedtuple's arity flag and its sub-flags merge in argv order

`--pt 1 2 --pt.y 9` and `--pt.y 9 --pt 1 2` used to produce three different merged dicts
between the two sides: vanilla promoted the arity list to the list-op shape
(`{'*': [1, 2], 'y': 9}`, which `build()` could not read then — `'*'` names no field) or
dropped the sub-flag outright, and the adapters merged the two halves order-independently,
so the flag the user typed last had no effect. The rule chosen: **the latest arguments
overwrite the earlier ones**, per path and in argv order — the same last-write-wins the other
[sub-flag rules](whole-value-then-subkey.md#a-whole-value-followed-by-a-subkey-opens-rather-than-collides) read:

- a sub-flag writes at `pt.y`, so it *refines* what is at `pt`: the arity flag's
  positional list becomes the `'*'` base and the sub-flag patches beside it —
  `{'*': [1, 2], 'y': 9}`, which builds `Pt(x=1, y=9)`;
- the arity flag writes at `pt`, so a later occurrence *replaces* the field wholesale —
  `{'pt': [1, 2]}`, the sub-flag gone, as any later write at a path drops what the path
  held.

Vanilla gets both from its sequential scan alone: `_set_nested` turns a plain list a later
write descends through into the `'*'` base, for a namedtuple as for a *varlen* collection or
a plain `tuple[int, int]`. The adapters' CLI channel is the same sequential scan over the
same argv ([CLI adapters](../cli-adapters/model.md#argv-is-the-only-writer)), so the same argv
produces byte-identical dicts on all five front-ends — interleavings included
(`--pt.x 1 --pt 7 8 --pt.y 2` is `{'*': [7, 8], 'y': 2}`), which the per-flag argv read-back
the adapters first used (`_arity_flag_writes_last`) could not describe (BUG-111).

## build() reconciles the positions with the patch

`typedload._construct._lay_patch_over_positions` is the one place a namedtuple's positional
base meets a patch, whichever channel wrote them: it keys the `'*'` list by field name and
lays the patch over it — an all-index patch by position, as a fixed tuple's, a name patch by
name, each value refining what the base holds at its position through
`_merge._merge_existing_value`. That is `Pt(*base)._replace(**patch)`, the stdlib's own
spelling of the same operation. A patch mixing names and indices still reaches the by-name
form with its index key, which refuses it — the open
[Q-1](../../todo/questions/Q-1-should-a-mixed-name-index-spelling-of-a-namedtuple-build.md).

The shape reaches `build()` from every channel because the merge cannot do better: it is
type-unaware ([merge/build contract](../pipeline/merge-build-contract.md#merge-build-contract)),
so a file's `pt: [1, 2]` under `--pt.x 9` or `APP_PT__X=9` is a list patched by a key that is
no index — a field for a namedtuple, an error for a list. `_merge._patch_needs_the_type`
defers it as `{'*': [1, 2], 'x': 9}`, beside the out-of-range index it already deferred for
the same reason (BUG-160).

The sub-flag's value is eagerly coerced, like every other leaf token. The adapters' former
collector used to store it raw, which put a `str` where vanilla stored the number and made
`--pt.y 9 --double '${pt.y * 2}'` fail on the four adapters (`'9' * 2` is `'99'`)
while vanilla said 18 — the gap PR #99 closed for the other leaves.

The alternatives, and why not:

- **Re-key the positional list by field name at parse time** (`_promote_namedtuple_positional`,
  BUG-66 to BUG-160). It made the CLI's dict buildable while `build()` could not read the
  `'*'` shape, and it was the rule here until BUG-160. Withdrawn: the parser is the only
  writer that knows the field is a namedtuple, so a file's or the env's list under a name
  patch still reached the merge as a list and failed there, and the same reconciliation had
  to exist in `build()` anyway. Two decision-makers then disagreed on the index patch:
  `--pt 1 2 --pt.0 9` re-keyed to the mixed `{'x': 1, 'y': 2, '0': 9}`, refused, where a
  file's `[1, 2]` under `--pt.0 9` built `Pt(9, 2)`.
- **Adopt the adapters' order-independent merge** (sub-flags always ride). Rejected: a
  flag the user typed last would vanish — the complaint that filed the bug — and
  vanilla would have to resurrect sub-flags an arity flag had already overwritten.
- **Store the sub-flag's token raw**, as the adapters did. Rejected: the merged dict
  would carry types no other channel produces, and an expression over the field would
  read the text.

The optional spelling is no different. `Point | None` is a union with a sequence variant to
the vanilla scan, and its positional run descends through the same `_set_nested`, so
`--pt 1 2 --pt.y 9` is `{'*': ['1', '2'], 'y': 9}` there too, and builds `Pt(1, 9)` on all five
front-ends. Under the parse-time re-keying it was the one spelling the promotion skipped (it
asked the field as resolved and found the union), and so the one that failed in `build()`.

## A base list carried with its patch replaces what lay below

A `'*'` dict in a higher layer says "this list, then these patches". `_merge_existing_value`
therefore lets it replace a dict base outright, as a union tag does, instead of deep-merging
into it: the base may be a name dict a file spelled (`pt: {x: 5}` under `APP_PT='[1, 2]'`
plus `APP_PT__Y=9` is `Pt(1, 9)`, not `Pt(5, 9)`), or a patch an earlier merge deferred, whose
stale index keys would otherwise survive (`{'*': [1], '1': 5}` under `{'*': [7, 9], '0': 8}`
built `(8, 5)` on a `tuple[int, int]` until BUG-160). `'*'` is a merge-op key
(`_pipeline._MERGE_OP_KEYS`), so no dict field's own key is read this way by surprise.

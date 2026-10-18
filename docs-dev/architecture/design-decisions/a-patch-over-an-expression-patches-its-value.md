# A patch over an expression patches its value

An expression that stands for a whole value is the value below a patch over it: the merge keeps it as the patch's `__base__`, and `build()` applies the patch to what it resolves to, by the merge's own combiner ([deep merge](../pipeline/deep-merge.md#a-patch-over-an-expression-patches-its-value)).
A file's `names: '${other}'` under `--names+ c` builds `other`'s items then `c`, and a file's `db: '${proto}'` under `--db.host x` builds `proto` with its `host` replaced, as they would over a file holding the resolved value.
It holds for every kind of patch and every layer: a list op, an index patch, a struct field, a dict key and its delete, a later file, and the environment writing the value then a key below it.

Until then a patch over an expression replaced it, since the merge read the expression as a scalar: `--db.host x` built `Db(host='x', port=0)` and `--m.a-` an empty dict, silently.
Only a file's own `__base__: '${other}'` worked, because construction applied its ops after resolution.
That contradicted the rule that a reference reads the value the field builds to: `names: '${other}'` *is* `other`'s list once resolved, so a patch over it should do what it does over that list.

## What is carried

Only a string that is one `${...}` and nothing around it is carried (`dictexpr.is_whole_expression`): an interpolation always resolves to a string, which a patch replaces as it replaces any scalar, so it keeps today's outcome without the carried form.
A whole value over the expression replaces it, as it replaces any value: `--names z` over `names: '${other}'` builds `['z']`.
A patch that names a new value, a union tag or a typed `call:`, replaces it too ([the type decides whether a value replaces or refines](the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)), and a `Callable` field opens the expression into `{bind: …}` first, as it opens any shorthand.

`merge()` stays as written: it holds `{ListOp.BASE: '${proto}', 'host': 'x'}`, which `dump_file` writes with the reserved key `__base__` and `merge(files=[...])` reads back as the same dict.
`__base__` so says "the value below the patch" for any value, where it said "the list below the ops"; a base that is no list still refuses a list op over it at construction, as a lower file holding a dict would.

## How build() settles it

The default layer lays nothing below a carried node: what lies below the patch is unknown until the expression resolves, and it replaces the field's default anyway.
Resolution settles the node the moment the last expression below it resolves (`resolve_expressions`' `settle` hook, `_default_layer.settle_pending`), and a reference to the node depends on every expression below it, so a reader sees the settled value: `${len(names)}` counts `other`'s items and `c`.
`dictexpr` still knows no type and no merge: the hook is handed the node and its position, and the default layer combines the two with `_merge._merge_existing_value`, typed by where the node stands.

An expression inside the patch that reads the patched node itself through a data key, `db: {__base__: '${proto}', host: '${.port}'}`, waits for the node it is part of, and is refused as a cycle ([limitations](../limitations.md#expressions)).

## Rejected

- **Refusing a patch over an expression**, with an error naming both writers.
  Cheap and honest, but it breaks the file's `__base__: '${other}'`, which worked, and leaves the expression no way to be refined.
- **Lists only**, keeping the struct and dict cases for later.
  It would have left two rules side by side for one question, a patch over a value the type reads.

## Precedents

Jsonnet's `{ db: self.proto } + { db+: { host: 'x' } }` patches the evaluated `db`: `+:` binds late to the value it refines, which is this decision.
No merge-before-interpolate library documented what it does in this case, so none is cited for the other side.

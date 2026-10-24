# A pending list op is applied before resolution

`build()`, `resolve()` and `from_dict()` apply every list op `merge()` left pending over what lies below it, the laid default where there is one and nothing where there is none, before an expression reads the list (`_default_layer._over_nothing`, BUG-220).
No layer lies below the defaults, so the list the ops make there is final, and it is the one construction would have built anyway.
So `${names[0]}` reads the item `--names+ a` appended, `${len(names)}` counts three items for `--names a b --names+ c`, and `${key(.)}` in an appended item reads its index ([values and references](../expressions/values-and-references.md#a-pending-list-op-is-read-as-its-list)).

Until then an expression read the op dict itself: `${names[0]}` found no key `0` in `{ListOp.APPEND: ['a']}`, and `${len(names)}` counted its keys, two for `{BASE: [a, b], APPEND: [c]}`, silently.
With a base file below, the merge had applied the append and the same reference read right, so a reference turned on whether some lower layer set the list.

## Where it applies

The ops are applied where the type settles that the node is a variable-length sequence: a list, a set, a `tuple[X, ...]`, the one non-`None` variant of an optional, a union whose variants taking a list op are all variable-length (`list[int] | dict[str, int]`, where only the list takes one and construction builds it), and the untyped `locals` namespace, where an op can only mean a list and nothing builds the node ([locals](../locals.md#a-list-op-in-a-namespace-is-its-list)).
An index-keyed dict with no gap reads as the list it spells too, so `--names.0 x` answers `${names[-1]}`.

Elsewhere an op stays pending for construction to apply or refuse, as before: at an `Any`, where `--a+` is refused and construction refuses a file's `__append__`; at a fixed tuple or a namedtuple, whose append and list delete construction refuses ([deep merge](../pipeline/deep-merge.md#no-channel-types-an-op)); below a union holding a fixed-length variant beside a list.
An expression reading such a node is refused (`MissingReferenceError.pending_list_ops`) instead of reading the op dict, so no residual case gives a silent wrong count.
An index delete with nothing to delete from is left for construction too, which refuses it with "requires a base list".

## A scalar append is one item

An op is applied before resolution, so a file's scalar `__append__: '${other}'` appends one item, whatever list `${other}` resolves to.
Construction applied it after resolution, and spread a list-valued expression over no base, while the merge across layers, argv and the environment all appended it as one item: the outcome turned on whether a base lay below.
A file that wants the items of `${other}` writes it as the base, `{__base__: '${other}', __append__: [c]}` or `names: '${other}'` below a layer appending ([a patch over an expression patches its value](a-patch-over-an-expression-patches-its-value.md)).
Precedents: JSON Patch's `add` at `/-` appends its `value` as one element, a list included; Python's `list.append` against `extend`.

## Rejected

- **The walk reads through the ops** (`dictexpr._step` viewing a pending node as its list), keeping `resolve()`'s output as it was.
  `_step` serves evaluation, the dependency scan and the write-back, and an expression inside an appended item sits at `items.__append__.0.name` for the scan but at `items.0.name` in the view: every reader would have to translate one naming into the other.
  An index patch over a struct item needs a typed merge to build the view, and `dictexpr` knows no type.
- **`merge()` applies a layer's own ops.**
  `merge()` is "save as written" ([api seams](../pipeline/api-seams.md#public-api-seams)): `dump_file(merge(...))` of `--names+ c` would write `names: [c]`, which replaces a lower file's list where `{__append__: [c]}` appends to it, the round trip BUG-202 settled.

The cost: `resolve()` holds no pending op where the type settles the list, which matters to nobody but a caller dumping it as a layer to merge over others, which is `merge()`'s output's job.

## Precedents

Every library with list operations applies them before an interpolation reads the list: Hydra applies its overrides while it composes and resolves `${...}` on access; jsonargparse applies `--list+=x` while it parses; a JSON Patch or a Kustomize patch is applied whole before anything reads the result.
confarg defers the ops only because `merge()` is untyped and a lower layer may still come, a saved merge put over other files; inside `build()` neither holds.

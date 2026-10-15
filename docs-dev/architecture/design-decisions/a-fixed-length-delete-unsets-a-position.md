# A fixed-length delete unsets a position

A delete at a position of a namedtuple or a fixed tuple unsets that position in place; nothing slides into it (BUG-243). A namedtuple field falls back to its class default, or is a missing field when it has none; a fixed tuple's position is `None` where its type takes `None`, and a missing field otherwise. With `class Pt(NamedTuple): x: int = 1; y: int = 2` and a file's `pt: [7, 8]`:

| | builds |
|---|---|
| `--pt.0-`, `--pt.x-`, `--pt.-2-`, `APP_PT__X-` | `Pt(1, 8)` |
| `--rq.x- --rq.x 1` (`Req` with no defaults) | `Req(1, 8)` |
| `--rq.x-` | `MissingFieldError` at `rq.x` |
| `--t.0-` on `t: tuple[int, int]` | `MissingFieldError` at `t[0]` |
| `--to.0-` on `to: tuple[int \| None, int]` | `(None, 8)` |
| `--t.0- --t.0 9` | `(9, 8)` |

Until then the delete was a list op (`{__delete__: [0]}`), which shortens a list: `--pt.0-` built `Pt(8, 2)`, `y` silently moved into `x`, `--t.0-` was "expected 2 elements, got 1", and `--pt.x-`, which the parser already wrote as a key delete, failed on the leaked sentinel. A fixed-length sequence has no length to shrink, so the only meaning a delete can keep there is the one it has on a struct field: `--sub.p-` falls back to the class's default for `p`.

## The delete removes the position from the default too

The default layer lays a field's default below every source ([a field default is the base layer](a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer)), and the delete reaches it: `pt: Pt = Pt(5, 6)` with `--pt.x-` builds `Pt(1, 6)`, and over a file's `[7, 8]` `Pt(1, 8)`. What is left is the type's own answer, the class default, exactly as a struct's instance default would leave the class's once it is laid (FEAT-39). A fixed tuple has no answer of its own, so its position is `None` or missing; reading the field default per position instead, `(1, 8)`, was rejected: a delete would then mean one thing over a file and another over nothing, and the tuple's default would act as per-position defaults it never declared.

## How each stage carries it

- **Argv and the environment** write a key delete at the key as spelled (`{"0": DICT_DELETE}`, `{x: DICT_DELETE}`): `_parse_cli._delete_index` counts a fixed-length node among the keyed kinds. A union takes the key delete only where every branch is a dict, a struct or fixed-length; a list, set or variadic tuple branch keeps the index delete, which the content below cannot be asked about yet ([Q-8](../../todo/questions/Q-8-should-a-delete-on-an-untyped-node-be-read-by-its-content.md)).
- **The merge** keys a base list once a delete unsets one of its positions (`_merge._unset_positions`): a list holds no hole, so the base becomes the dict construction already reads for a fixed-length type, a namedtuple's by field name, a fixed tuple's by index, and the delete stays at the position it unset: `pt: {x: DICT_DELETE, y: 8}`, which `dump_file` writes as `x: {__unset__: true}` and reads back. At a fixed-length node `_deep_merge` keeps every delete where it stands, where elsewhere it spends it on the base and drops it, and `_spent_if_met` never spends one: the field default below still holds the position, and only the delete keeps it from showing through. A later write at the position, in any spelling ([which keys are one key](../pipeline/deep-merge.md#which-keys-are-one-key)), replaces it.
- **The default layer** merges the field default under the keyed form, which takes the position out of the default, and drops the delete, met; one that met no laid default is dropped as any unmet delete is (BUG-98). It then lays, at each position left unset, what construction fills it with, `typedload._construct.unset_position`, so `${pt.x}` reads 1, the value `pt.x` builds to; the two ask one function and cannot drift.
- **Construction** reads a delete at a position as the position unset, under a carried base too, and fills it by `unset_position`.

## A file's list delete is refused there

`pt: {__delete__: [0]}` and `__delete_after__` are refused on a fixed-length node, naming `{"0": {__unset__: true}}`, by the merge over a base list (`_merge._refuse_a_position_list_delete`) and by construction (`_apply_carried_ops`): a file spells the unset at the position, one spelling for one meaning, and the list delete would shift. An `__append__` over a carried base still applies and is checked against the arity. FEAT-43's refusal of a bare `"0": {__unset__: true}` stays for a list, whose index it would leave empty, and is lifted for a fixed-length node, where an unset position is the meaning.

## Rejected

- **Refusing a fixed-length delete at parse**, with a hint to set the position: a file already spelled `pt: {x: {__unset__: true}}`, which would have had to be refused too, and a struct field's delete already had this meaning.
- **Deferring the delete beside its base**, `{__base__: [7, 8], x: DICT_DELETE}`: `_deep_merge` drops a delete the base holds when a higher layer merges over the node, so `APP_PT__X-` under `--pt.y 5` lost it.
- **Dropping the delete once it met the base list**, leaving `{y: 8}`: the default layer then lays the field default under it as under any patch, and `Pt(5, 6)`'s `x` showed through.

Precedent: `NamedTuple._replace` sets a field and never removes one; a dataclass field's delete in confarg already fell back to the class default.

# An argv delete is shaped by the type

Argv and the environment spell an index delete and a key delete with one suffix (`--xs.1-`, `--d.k-`, `APP_D__1-`), while the merge holds them in two shapes: an index delete is a list op of the node above it (`{__delete__: [1]}`, `__delete_after__` when it follows an append in the same source), a key delete is the delete sentinel at the key (`{"k": DICT_DELETE}`, which a file spells `k: {__unset__: true}`).
**The parser chooses the shape at parse time, by the type the walk reaches** (`_parse_cli._delete_index`, [collection patches](../cli-parsing/collection-patches.md#the-type-decides-what-a-delete-removes)); where no type describes the node, the segment's spelling chooses: an index as `str()` writes one is an index delete.

## Why two shapes

The list op keeps what argv can say about a list.
An index delete counts the positions of the list below, before any append (`__delete__`) or after the appends typed before it (`__delete_after__`), and an index patch counts the positions after both, so one source can delete an item and patch what slides into its place:

| argv over `[a, b, c]` | builds |
|---|---|
| `--xs.0- --xs.0 X` | `[X, c]` |
| `--xs.-1- --xs.-1 X` | `[a, X]` |
| `--xs.0- --xs.1- --xs.0 X` | `[X]` |
| `--its.0- --its.0.name z` (a list of structs) | the item that slid into 0, renamed |
| `--xs+ d --xs.-1-` | `[a, b, c]`: the appended item deleted |
| `--xs.-1- --xs+ d` | `[a, b, d]`: the last item replaced |

## What it costs

- A parser must tell a list from a dict without the data, so on a node no type describes, an `Any`, a callable's spec, a union whose list and dict variants both take the segment, the spelling decides.
  `--a.1-` deletes index 1 of an `Any` holding a list, and is refused on one holding a dict with the key `1`, which argv and the environment then cannot delete ([Q-8](../../todo/questions/Q-8-should-a-delete-on-an-untyped-node-be-read-by-its-content.md)).
  A file can: `a: {"1": {__unset__: true}}`.
- `__delete__` is a key of the node above the one it deletes, unlike every other op, which is why a file spells an index delete there and not at the index ([a file spells an op in its value](a-file-spells-an-op-in-its-value.md#where-a-delete-has-no-meaning)).

## Rejected

- **One shape, the key's, read by the content below**: `--xs.1-` writes `{"1": DICT_DELETE}` like `--d.1-`, and the merge reads it as an index delete over a list, as RFC 6902's `remove` reads a JSON Pointer against the document it patches.
  No parser would choose, and a dump would have one spelling.
  But a delete and a patch at one index would share one key, so every chain of the table above loses an op or changes meaning within one source: `--xs.0- --xs.0 X` would build `[X, b, c]`, and the environment's `APP_XS__0-` beside `APP_XS__0=X` would keep whichever its order wrote last.
  It also reverses FEAT-43's refusal of `"N": {__unset__: true}` under a list.
  Its one gain, replacing an item whole from argv, is already there for a struct item, whose restated tag replaces what lies below (`--its.0.class pkg.It --its.0.name z`), and is missing only for a dict or an `Any` item.
- **One shape, the list op's**: `--d.k-` writes `{__delete__: ["k"]}` in the parent, read against the content below.
  Every list chain survives, but the key-delete machinery moves from the key to its parent (`_spent_if_met`, `_written_over`, `_keep_deletes`, `_without_key_deletes`, the serializer), a mounted fragment deleting the node it stands at has no parent to write into, and `--d.k 3 --d.k-` must drop the earlier write itself.
  It is the "delete spelled from the parent" FEAT-43 rejected.
- **A third, deferred shape** where no type decides, resolved by the merge against what lies below, as a value patch on an `Any` already is (`--a.1 99` patches index 1 of a list and the key `1` of a dict).
  It needs a marker every reader of ops must know, and `dump_file` has no file spelling for "an index or a key, whichever fits" to write one a merge left pending.
  Q-8 keeps the question open for the untyped node alone.

## Precedents

- **RFC 6902 (JSON Patch)** and OmegaConf delete by content, against a document already composed: a path segment names an array index or an object member according to what the document holds. confarg parses a channel before the layers below it are merged, so it has the type to go by and not yet the content.
- **MongoDB** keeps the two apart: `$unset` removes a field, `$pull` removes array elements.
- **Kubernetes' strategic merge patch** has both: a per-node `$patch: delete` and parent-level directive lists (`$deleteFromPrimitiveList/<field>`, `$retainKeys`).

# A file spells an op in its value

Argv and the environment spell a merge op on a **path**: a flag's or a variable's name (`--xs+`, `--name-`, `--xs.0-`, `APP_XS+`, `APP_NAME-`), which is never data. A configuration file has no path apart from its keys. Until FEAT-43 it spelled the op in a **key** (`xs+:`, `name-:`, `"0-":`), so a file key was a path and a datum at once, and every difficulty around Q-7 came from that overlap:

- each channel decided on its own which strings were ops, and they disagreed (Q-7, BUG-228, BUG-201, BUG-237);
- no file could give a dict a key ending in `+` or `-`, and a dict holding one did not survive `dump_file` and a reload;
- a merged key delete had no spelling a dump could write that a data key could not also mean (BUG-202);
- reading a dict was not idempotent (`a--` read as a delete of `a-`, and read twice as a delete of `a`), so each dict of a document had to be read exactly once, in the right order around its includes.

**A file spells every merge op in the value, as a reserved key of the dict standing at the op's path. Every other key of a file is data.** Argv and the environment keep their suffixes, which sit on a path and collide with nothing.

| Op | In a file | On argv | In the environment |
|---|---|---|---|
| append | `xs: {__append__: [3]}` | `--xs+ 3` | `APP_XS+=3` |
| delete an index | `xs: {__delete__: [0]}` | `--xs.0-` | `APP_XS__0-` |
| delete a node | `name: {__unset__: true}` | `--name-` | `APP_NAME-` |
| delete a node, then write keys | `sec: {__unset__: true, a: 1}` | `--sec- --sec.a 1` | `APP_SEC-`, `APP_SEC__A=1` |
| delete a list, then append | `xs: {__unset__: true, __append__: [9]}` | `--xs- --xs+ 9` | `APP_XS-`, `APP_XS+=9` |

`__base__` and `__delete_after__` keep the meaning they had: they are the spellings `dump_file` writes a merged dict's pending ops with ([deep merge](../pipeline/deep-merge.md#no-channel-types-an-op)). `c++: 1` in a file is the key `c++`, `a-` the key `a-`, and `"0-"` the key `0-`, at any depth, in a `dict` or an `Any`; a struct refuses one as the unknown field it is, as it would a misspelled one, with no hint and no migration message, as for a decoded value ([a decoded value is data](a-decoded-value-is-data.md#a-decoded-value-is-data)).

## The node delete

`__unset__` deletes the node it stands in from the layers below. Its value must be `true`: `false`, `null` or anything else is refused, so `{__unset__: false}` has no meaning to guess. Beside other keys, the node is deleted first and the rest written over the delete, as a dict written over a key delete in one source is (`_merge._written_over`): `{__unset__: true, a: 1}` reads as `{__base__: DICT_DELETE, a: 1}`, the shape a `--sec- --sec.a 1` pair already makes, and replaces what lies below with `{a: 1}`. An `__include__` beside it is part of the rest: the delete applies first, then the include and its siblings. A list or a scalar written over it replaces it, as `--x- --x 5` does.

`_serialize._serialize_untyped` writes a delete the merged dict still holds in the same spelling, so it survives `dump_file` and a reload (BUG-202). `_files._resolve_dict` reads it, before the rest of the dict, which it resolves first; `_merge._read_file_ops` reads the four list ops of what is left. Both read a dict once its values are resolved, and both are idempotent, so the read-each-dict-once rule the suffixes needed is gone.

A mounted fragment whose root is a delete (`del.yaml` holding `__unset__: true`) is a key delete in the source that includes it. Siblings beside its `__include__`, and a later entry of an `__include__` list, are written over it as a dict is written over a delete in the same file (`_merge._written_within_source`), so `name: {__include__: del.yaml, b: 2}` reads as `name: {__unset__: true, b: 2}`.

## Where a delete has no meaning

A bare delete is refused wherever it would delete nothing, or would be a second spelling of something that has one:

- **A document root**, alone or beside keys, included or not (`_files._require_layer`): a layer is merged over the layers below it and cannot cut them off. A mounted fragment or an included file standing at a node may hold one, since its root is that node's value; so may `__root__` at a document root, a key like any other there.
- **Beside `__base__`**: both say what lies below the node, two bases.
- **As the value of `__base__`**: a base is a list, and `{__base__: {__unset__: true}, __append__: [1]}` would be a second spelling of `{__unset__: true, __append__: [1]}`.
- **A list item**, an item of an `__append__`, a single appended value, and an item `--config.xs+` or `CONFIG__XS+` appends (`_merge._as_list_item`): an item has no layer below it, so it deletes nothing, and dropping it would drop an item silently. An item with keys beside the delete keeps those keys, the delete removed (`_merge._without_key_deletes`).
- **A bare index patch under a list**, `xs: {"0": {__unset__: true}}`: it would leave nothing in the slot, so it could only remove the item, a list op with a spelling of its own, `__delete__: [0]`. It is refused naming that spelling, by the index readers of the merge (`_merge._apply_list_ops`) and of construction (`typedload._construct._indexed_dict_to_positions`, and `_build_items` for a list built from index keys alone), since only the type tells a list from a dict. Under a dict, `"0"` is a key like `a`, and its delete removes it; under a fixed tuple or a namedtuple, it unsets the position, which keeps its place ([a fixed-length delete unsets a position](a-fixed-length-delete-unsets-a-position.md#a-files-list-delete-is-refused-there)). A delete spelled as a patch key would also count its index after the deletes and the appends, as every patch key does (`{__delete__: [0], "0": X}` over `[a, b, c]` builds `[X, c]`), beside a `__delete__` counting it before them.

An index patch with keys beside the delete, `xs: {"0": {__unset__: true, k: 5}}`, is not refused: the old item lies below it, and the patch replaces it rather than merging into it, which is that replace's one file spelling. Argv has none: `--xs.0 '{…}'` merges.

`__unset__` joins `_defaults.RESERVED_KEYS`, so a flag, a variable, a mount point and a decoded JSON value refuse it like the others ([reserved keys](../config-files/reserved-keys.md#reserved-file-only-keys)), and so does a CSV/TSV header where a name becomes a dict key: a data file is the file channel's data.

## What it costs

- Every file spelling `key+:`, `key-:` or `"N-":` changed meaning, silently where a `dict` or an `Any` holds the key. The library had not shipped.
- Files are more verbose: `xs: {__append__: [3]}` for `xs+: [3]`.
- A file can no longer order two ops on one key within one dict: YAML, TOML and JSON hold a key once, so `{x: 1, x-: null}` and `{xs+: [1], xs-: null}` have no spelling. The ops of one value apply in the fixed semantic order (the delete of the node, then the base, the index deletes, the appends, the post-append deletes, the index patches), and the one order left is the one that means something.
- The dunder names stay unavailable as data on every channel, `__unset__` added.

## Precedents

- **Kubernetes' strategic merge patch** puts the directive in the value, in the same shape: `name: {$patch: delete}`, `$patch: replace` beside the keys that replace, and `$`-prefixed keys reserved. `{__unset__: true, …}` is its `replace`.
- **Docker Compose** marks the value, with the YAML tags `!reset` and `!override`; [FEAT-44](../../todo/features/FEAT-44-yaml-tags-for-a-files-merge-ops.md) keeps the door open to the same.
- **OmegaConf and Hydra** keep a YAML key data always, by keeping ops out of files altogether (`+key`, `~key` only in the override grammar, `list_merge_mode` per call). That is the stronger form of this decision; a file here still patches.
- **JSON Merge Patch (RFC 7396)** and **Helm** spell a delete in band as `null` and accept that no patch can set a `null`: the cautionary case for an op that takes a value's spelling, which a dunder key never does.

## Rejected

- **Keep the suffixes and add an escape** for a literal key. The non-idempotent read and the dump's ambiguity stay; the escape only routes around them.
- **Merge behavior declared by the field's type** (`Annotated[list[str], Merge.APPEND]`), files spelling no op at all, as OmegaConf does. Cleaner still, but a file loses "append here, replace there". It composes with this decision and can come later.
- **A separate patch document or op stream** (Kustomize patches, RFC 6902). The most expressive and the heaviest to write; [FEAT-4](../../todo/features/FEAT-4-ordered-patch-op-stream.md)'s question.
- **`__reset__`**, after Compose's `!reset`: it fits, the field default being the base below, but reads as setting something back.
- **`__delete__: true`** beside `__delete__: [0]`: one verb, but the value's shape would choose the meaning.
- **A delete spelled from the parent**, `{__delete__: [name]}`: a `dict[int, …]` key and a list index collide.
- **`__patch__: delete`**, Kubernetes' spelling: a second key whose values are themselves a vocabulary.
- **`__unset__` alone only**: a file would lose the replace it spelled with `k-:` then `k:`.
- **`"N": {__unset__: true}` as an index delete**, matching `--xs.N-`: the merge would need the type to tell a list from a dict, which argv's delete takes from the walk at parse time ([an argv delete is shaped by the type](an-argv-delete-is-shaped-by-the-type.md#an-argv-delete-is-shaped-by-the-type)), and it would count its index unlike `__delete__` ([above](#where-a-delete-has-no-meaning)).
- **Refuse an index patch with keys beside the delete too**, for one rule at an index: a file would lose the one spelling of replacing an item whole.

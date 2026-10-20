# Plan — A file spells a merge op in its value

**Drafted:** 2026-10-14 · **Status:** FEAT-43 and BUG-202 built ([a file spells an op in its value](../../architecture/design-decisions/a-file-spells-an-op-in-its-value.md#a-file-spells-an-op-in-its-value)) · **Ticket:** FEAT-43, then BUG-202 and [BUG-241](../bugs/BUG-241-a-dict-key-named-like-a-reserved-key-dumps-as-the-key-a-file-reads.md)

## Where the problem comes from

Argv and the environment spell a merge op on a **path**: a flag's or a variable's name (`--xs+`, `APP_NAME-`), which is never data. A configuration file has no path apart from its keys, so it spells the op in a **key** (`xs+:`, `name-:`, `"0-":`), and a file key is a path and a datum at once. Every difficulty met around Q-7 comes from that one overlap:

| Symptom | Where it surfaced |
|---|---|
| Each channel decided on its own which strings were ops, and they disagreed | Q-7, BUG-228, BUG-201, BUG-237 |
| No file can give a dict a key ending in `+` or `-` | [limitations](../../architecture/limitations.md#collections) |
| `dump_file` cannot write such a key faithfully, nor a merged key delete | BUG-202, the dump refusal held back after BUG-239 |
| Reading a dict is not idempotent (`a--` is a delete of `a-`, read twice a delete of `a`), so each dict had to be read exactly once, in the right order around its includes | [a decoded value is data](../../architecture/design-decisions/a-decoded-value-is-data.md#how-it-is-built) |

**Decision: a file spells every merge op in the value, as a dunder key of the dict standing at the op's path. Every other key of a file is data.** Argv and the environment keep their suffixes, which sit on a path and collide with nothing.

## The vocabulary

| Today, in a file | Under this plan |
|---|---|
| `xs+: [3]` | `xs: {__append__: [3]}` (already read today) |
| `xs: {"0-": null}` | `xs: {__delete__: [0]}` (already read today) |
| `name-: null` | `name: {__unset__: true}` (new) |
| `name-: null` then `name: {a: 1}` in one dict | `name: {__unset__: true, a: 1}` |
| `xs-: null` then `xs+: [x]` | `xs: {__unset__: true, __append__: [x]}` |
| `__root__+: [3]` | `__root__: {__append__: [3]}` |
| `tags+: {__include__: rows.yaml}` | `tags: {__append__: {__include__: rows.yaml}}` |
| `c++: 1` (an append to the key `c+`) | `c++: 1`, the key `c++` |
| `__base__`, `__delete_after__` | unchanged: the spellings `dump_file` writes a merged dict's pending ops with |

`--xs+`, `--name-`, `--xs.0-`, `APP_XS+`, `APP_NAME-`, `--config.xs+`, `APP_CONFIG__XS+` are unchanged.

## Decisions taken

| # | Question | Decision |
|---|---|---|
| 1 | The key delete's spelling | `{__unset__: true}`. The value must be `true`: `false`, `null` or anything else is refused, so `{__unset__: false}` has no meaning to guess. `_defaults.UNSET_KEY` joins `RESERVED_KEYS`, so argv, the environment, a mount point and a decoded JSON value refuse it like the others. |
| 2 | `__unset__` beside other keys | Allowed: nothing below, then the rest. `{__unset__: true, …rest}` reads as `_merge._written_over(DICT_DELETE, rest)`, which is `{__base__: DICT_DELETE, …rest}`, the shape a `--sec- --sec.a 1` pair already makes. An `__include__` beside it is part of the rest: the delete applies first, then the include and its siblings. `__unset__` beside `__base__` is refused, as two bases. |
| 3 | `"N": {__unset__: true}` under a list | Refused: an index delete is `__delete__: [N]` alone. Under a dict it deletes the key `"N"`, as any key delete does. |
| 4 | A CSV/TSV header naming a reserved key | Refused, as a decoded JSON value refuses one: a data file is the file channel's data. |
| 5 | A data key named like a reserved key, in a dump | `dump()` refuses it, at any depth, naming its path; `dump_file` of an instance goes through `dump()` (BUG-241). A raw dict passed to `dump_file` is a document and is never refused: its string `"__append__"` is the op, its `xs+` a key, as a file reads them. |
| 6 | The old shorthand in a file | Plain data, with no hint and no migration message, as for a decoded value (Q-7's decision 8A): a struct refuses `xs+` as the unknown field it is, a `dict` or an `Any` holds it. |
| 7 | YAML tags (`xs: !append [3]`, `name: !unset`) | Out of scope; a FEAT is filed with the first revision. |
| 8 | `examples/` | Migrated with the code, since the markdown-console replay runs them. |
| 9 | Revisions | One per ticket: FEAT-43, then BUG-202, then BUG-241. |

Corners settled with the decisions above, since each follows from one of them:

- **A document root** holding `__unset__` is refused by `_require_layer`, as a root that is no mapping is: a layer is merged over the layers below it and cannot cut them off. A mounted fragment or an included file standing at a node may hold it, since its root is that node's value.
- **A list item** has no layer below it ([deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics)). An item that is a bare `{__unset__: true}` is refused: it deletes nothing, and dropping it would drop an item silently. An item with keys beside the delete keeps those keys, its `__base__: DICT_DELETE` removed as `_merge._without_key_deletes` removes a key delete there today. The items of an `__append__` are list items.
- **An index patch under a list** (`xs: {"0": …}`) has the old item below it. `"0": {__unset__: true, …rest}` replaces the item with the rest rather than merging into it, the one file spelling of that replace. A bare `"0": {__unset__: true}` would leave nothing in the slot, so it could only remove the item, a list op with a spelling of its own, `__delete__: [0]`; it is refused, naming that spelling (decision 3). A delete spelled as a patch key would also count its index after the deletes and the appends, as every patch key does (`{__delete__: [0], "0": X}` over `[a, b, c]` builds `[X, c]`), beside a `__delete__` counting it before them.
- **A mounted fragment that is a delete** (`del.yaml` holding `__unset__: true`) is a key delete in the source that includes it. Siblings beside its `__include__`, and a later entry of an `__include__` list, are written over it as a dict is written over a delete (`_merge._written_over`): `name: {__include__: del.yaml, b: 2}` reads as `name: {__unset__: true, b: 2}`. A list or a scalar written over it replaces it, as `--x- --x 5` does, so `{__unset__: true, __include__: rows.csv}` is the rows.
- **Where a bare delete means nothing** it is refused: as the value of `__base__` (a second spelling of `{__unset__: true, …}`; a base is a list), as the value of `__append__` or an item of it, and as an item appended by `--config.xs+` or `CONFIG__XS+`. As the value of `__root__` it is a key delete like any other, deleting the root value of the layers below.
- **A CSV/TSV header** is refused where a name becomes a dict key (several columns, or `orient: columns`); a one-column `orient: rows` file, which builds a plain list, and `orient: raw` use no name and are read as they are.
- **Two ops on one key in one dict** cannot be ordered any more: YAML, TOML and JSON hold a key once, so `{x: 1, x-: null}` and `{xs+: [1], xs-: null}` have no spelling. The ops of one value apply in the fixed semantic order (`__unset__`, then the base, the deletes, the appends, the post-append deletes, the index patches), and the one order left is the one that means something.
- **Index patch keys** (`xs: {"1": 5}`) are untouched: they are read by the field's type, not by their spelling ([limitations](../../architecture/limitations.md#collections)).
- **A decoded value** (`--d '{…}'`, `APP_D='{…}'`) is still data and still refuses every reserved key ([a decoded value is data](../../architecture/design-decisions/a-decoded-value-is-data.md#a-decoded-value-is-data)), `__unset__` included.

## Earlier decisions, read through this one

| Decision | Under this plan |
|---|---|
| Every structured value from argv or the environment is data (Q-7) | Stands. |
| Only the file channel reads ops | Stands, and simplifies: a dunder key read twice reads the same, so the "read each dict exactly once" rule and its note go. The read stays in `_files._resolve_dict`, where an include's content is resolved before the dict holding it is read. |
| A reserved key in a decoded value is refused | Stands, `__unset__` included. |
| `dump_file` refuses what it cannot write, with a FEAT for a file-side escape | Shrinks to a data key named like a reserved key (BUG-241). This plan is the escape, so no FEAT. |
| Every dict of a file reads ops, a list's items included (BUG-237) | Stands, for the dunder keys. |
| BUG-239, the environment's `+` (FEAT-18), a CSV header is data | Unaffected; a header naming a reserved key is now refused (decision 4). |
| "This is the way to give a dict a key ending in `+` or `-`" ([a decoded value is data](../../architecture/design-decisions/a-decoded-value-is-data.md#a-decoded-value-is-data)) | A file becomes one more way. The limitation "a file cannot give a dict a key ending in `+` or `-`" goes. |
| "`+` names the merge axis the same way in every channel" ([plus is a merge operator](../../architecture/design-decisions/plus-is-a-merge-operator.md)) | **Amended**: every channel spells the op on the path, and a file, whose keys are its paths and its data at once, spells it in the value. The note keeps its argument against dropping `+` from argv. |

## Precedents

- **Kubernetes' strategic merge patch** puts the directive in the value, in the same shape: `name: {$patch: delete}`, `$patch: replace` beside the keys that replace, and `$`-prefixed keys reserved. `{__unset__: true, …}` is its `replace`.
- **Docker Compose** marks the value, with the YAML tags `!reset` and `!override`; decision 7 leaves the door open to the same.
- **OmegaConf and Hydra** keep a YAML key data always, by keeping ops out of files altogether (`+key`, `~key` only in the override grammar, `list_merge_mode` per call). That is the stronger form of this plan; a file here still patches.
- **JSON Merge Patch (RFC 7396)** and **Helm** spell a delete in band as `null` and accept that no patch can set a `null`: the cautionary case for an op that takes a value's spelling, which a dunder key never does.
- **tomli_w** refuses a value it cannot represent rather than writing an approximation, the shape of BUG-241's refusal.

## Rejected

- **Keep the suffixes and add an escape** for a literal key. The non-idempotent read and the dump's ambiguity stay; the escape only routes around them.
- **Merge behavior declared by the field's type** (`Annotated[list[str], Merge.APPEND]`), files spelling no op at all, as OmegaConf does. Cleaner still, but a file loses "append here, replace there". It composes with this plan and can come later.
- **A separate patch document or op stream** (Kustomize patches, RFC 6902). The most expressive and the heaviest to write; [FEAT-4](../features/FEAT-4-ordered-patch-op-stream.md)'s question.
- **`__reset__`**, after Compose's `!reset`: it fits, the field default being the base below, but reads as setting something back.
- **`__delete__: true`** beside `__delete__: [0]`: one verb, but the value's shape would choose the meaning.
- **A delete spelled from the parent**, `{__delete__: [name]}`: a `dict[int, …]` key and a list index collide.
- **`__patch__: delete`**, Kubernetes' spelling: a second key whose values are themselves a vocabulary.
- **`__unset__` alone only**: a file would lose the replace it spells today with `k-:` then `k:`.
- **`"N": {__unset__: true}` as an index delete**, matching `--xs.N-`: the merge would need the type to tell a list from a dict, which is what [BUG-174](../bugs/BUG-174-an-index-delete-on-a-dict-writes-the-list-delete-key.md) shows the CLI getting wrong.
- **A refusal in `dump_file` only**: `dump()` promises a config-compatible dict.

## What it costs

- Every file spelling `key+:`, `key-:` or `"N-":` changes meaning, silently where a `dict` or an `Any` holds the key. The library has not shipped.
- Files are more verbose: `xs: {__append__: [3]}` for `xs+: [3]`.
- A file can no longer order two ops on one key within one dict.
- The dunder names stay unavailable as data on every channel, `__unset__` added.

## Build order

### 1. FEAT-43: the reader

1. `_defaults.UNSET_KEY = "__unset__"`, added to `RESERVED_KEYS`.
2. `_merge._normalize_merge_ops` reads the dunder keys only: the four op keys become their markers, `__unset__` is checked (`true`, no `__base__` beside it) and becomes `DICT_DELETE` alone or `_written_over(DICT_DELETE, rest)` with keys beside it. The suffix branches, `_apply_append_key` and `_merge_regular_key` go; `_spent_if_met` stays for argv, the environment and `_keep_deletes`. Rename it after what it does now (`_read_file_ops`), and drop the idempotence paragraph from its docstring.
3. `_files._resolve_dict`: a dict holding `__unset__` resolves its include and its siblings first, then applies the delete before them (decision 2). `_require_layer` refuses a root that holds a delete. The list branch refuses a bare-delete item and strips the base of one with keys beside it (`_without_key_deletes`).
4. The CSV/TSV header refuses a reserved name, through `_cast._refuse_reserved_keys` or a shared check beside it.
5. A delete at an index key under a list is refused, at the one index reader each side has: the merge's index patch (`_apply_list_ops`) and construction's (`typedload._indexed_dict_to_positions`).
6. Tests: migrate every file shorthand (`tests/test_merge.py`, `tests/test_include.py`, `tests/cli/test_backend_contract.py`, `tests/test_coverage_gaps.py`, `tests/test_env.py`'s file fixtures); add the decisions above, each corner included, with a `c++` and an `a-` key round-tripping through a file; the backend contract suite for the channel parity of `__unset__` against `--name-` and `APP_NAME-`.
7. Examples: `examples/16_appending_items/more_ints.yaml` and its README, `examples/11_include/README.md`.
8. Architecture notes: a new design decision, `a-file-spells-an-op-in-its-value.md`, carrying this plan's rationale, rejected alternatives and precedents, with its row in the design-decisions README; then [deep merge](../../architecture/pipeline/deep-merge.md) (the shorthand bullet, the op table's "produced by" column, the within-source and list-item paragraphs), [reserved keys](../../architecture/config-files/reserved-keys.md), [a decoded value is data](../../architecture/design-decisions/a-decoded-value-is-data.md), [plus is a merge operator](../../architecture/design-decisions/plus-is-a-merge-operator.md), [merge ops are markers](../../architecture/design-decisions/merge-ops-are-markers-no-channel-types.md), [include semantics](../../architecture/config-files/include-semantics.md), [a field default is the base layer](../../architecture/design-decisions/a-field-default-is-the-base-layer.md), [limitations](../../architecture/limitations.md), [invariants](../../architecture/invariants.md), and whatever `grep -rnE '[A-Za-z0-9_"]+[+-]"?:'` still finds in `docs-dev/` and in the docstrings of `src/`. The FEAT-23 and untyped-config-rewriter plans name the vocabulary; correct them where they name a file's shorthand.
9. File the YAML-tags FEAT ([FEAT-44](../features/FEAT-44-yaml-tags-for-a-files-merge-ops.md)). Close REF-87 in the same revision: `_apply_append_key`, one of its two combiners, is gone.

### 2. BUG-202: the dump writes a key delete

`_serialize_untyped` writes `DICT_DELETE` (either instance) as `{__unset__: true}`, and a dict holding `__base__: DICT_DELETE` as `__unset__: true` beside its other keys, so `merge(files=[dump_file(merge(…))])` gives the merged dict back. Test first, from the ticket's reproduction.

### 3. BUG-241: the dump refuses a reserved data key

`dump()` refuses a key of `RESERVED_KEYS` in a dict it serializes, at any depth, with its path. Test first, from the ticket's reproduction.

## How to tell it worked

- Every reproduction above passes, and so does a round trip of a dict holding `c++`, `a-` and `"0-"` through `dump_file` and `merge(files=[…])`, in YAML, TOML and JSON.
- A file's `xs: {__append__: …}`, `name: {__unset__: true}` and `xs: {__delete__: [0]}` give the same merged dict as `--xs+`, `--name-` and `--xs.0-`, in every front-end.
- The full suite, pre-commit and `ty` pass; the markdown-console replay passes on the two migrated examples.
- `grep -rnE '[A-Za-z0-9_"]+[+-]"?: '` finds no file shorthand left in `docs-dev/`, `examples/`, `src/` or `tests/`, other than as data.

## Tickets this touches

- [BUG-174](../bugs/BUG-174-an-index-delete-on-a-dict-writes-the-list-delete-key.md): its file side is fixed by decision 3 (a file's `d: {"1": {__unset__: true}}` deletes the key); its argv and environment side stays open.
- [BUG-220](../bugs/BUG-220-a-reference-into-a-list-with-pending-ops-reads-none-of-its-items.md), [FEAT-4](../features/FEAT-4-ordered-patch-op-stream.md) and [FEAT-23](../features/FEAT-23-post-resolve-transform-layer.md): unchanged; the ops this plan spells are the markers they reason about.

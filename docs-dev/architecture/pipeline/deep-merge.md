# Deep merge

## Deep merge semantics

`_merge._deep_merge(base, override)` is recursive, **dict-wins**: the override replaces
anything that is not a dict-on-dict, which is merged recursively.

- **A value of its own in the override discards the base entirely.** Whether a dict is one is the type's to say, as construction will read it there (`_merge.MergeAt`, typed by `_typed_merge.TypedAt`; [design decisions](../design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)). A union tag naming a class says "this is a new object", so fields of the previous variant must not leak in (the README's `--class myapp.SQLiteConfig --dbpath …` over a server config). A `call:` is a finished value, so no key a lower layer set beside it can belong to it, whatever lay below: a dict, a list or another call (BUG-190, [design decisions](../design-decisions/a-call-replaces-what-lies-below.md#a-call-replaces-what-lies-below)). An opener on a Callable or an `Any` names a new target, so the old target's arguments do not follow it (BUG-231). A layer holding only `args`, or an opener holding a dict with no opener of its own, refines the spec below it as any dict-on-dict does. Where the type holds the key as data, a `dict` field or a struct owning the key's spelling, the dict refines too (BUG-232); where the merge cannot type the node, the tag and `call` replace by key.
- **A shorthand below a refining dict opens.** A bare string a Callable reads as `{bind: <string>}` is opened into that form when a higher dict refines it, so `--fn.args.punct !` over a file's `fn: pkg.shout` keeps the target (`MergeAt.opened`), as the two flags do within one argv ([below](#scalar-intermediates)).
- **A base list carried with its patch discards a dict base.** An override holding the
  `__base__` op is "this list, then these patches", so it replaces a name dict or an earlier
  deferred patch rather than merging into it
  ([design decisions](../design-decisions/namedtuple-arity-flag-argv-order.md#a-base-list-carried-with-its-patch-replaces-what-lay-below)).
  A `__base__` of `DICT_DELETE` discards a list base too: it is a whole-field delete with
  ops after it ([below](#an-op-after-a-whole-field-delete-has-nothing-below-it)).
  Over a list base, the override's own base replaces it as well; a patch beside it whose meaning
  is the type's — a name key, an index past the base — stays deferred with it rather than being
  applied as list ops, as the same override over no lower layer is (5a, found fixing BUG-221:
  `--pt 1 2 --pt.y 5` over `APP_PT='[7, 8]'` read `y` as a list index).
- **A cast pin replaces what lies below.** A file's `{__cast__, __value__}` is a value, so it
  replaces a list or a dict a lower layer held, as a scalar would, rather than being merged
  into it as a patch (5b: two files, `u: [1, 2]` then a pin, deferred the pin's keys as a
  patch of the list). The merge tells it by shape alone (`_is_pin_dict`), whatever the
  type; construction resolves the pin, as it does wherever one stands (BUG-210). A pin below
  is a value too: a dict over it replaces it, as a dict over the plain `5` does, rather than
  merging into the pin's two keys, which an `Any` field then held as data (BUG-239).
- `DICT_DELETE` (from a file's `key: {__unset__: true}`, `--field.key-`, `FOO__KEY-`) removes a key.
- A file spells the ops in the value, as reserved keys of the dict at the op's path: `_files._resolve_dict` reads `__unset__`, the node delete, and `_merge._read_file_ops` the four list ops below, the ops argv and the environment spell on their paths, so the three channels share one patch vocabulary. Every other key of a file is data, `xs+` and `a-` included ([design decisions](../design-decisions/a-file-spells-an-op-in-its-value.md#a-file-spells-an-op-in-its-value)). Only a configuration document is read, as the include walk leaves it; no merge reads a key, so a value argv or the environment decodes is data ([design decisions](../design-decisions/a-decoded-value-is-data.md#a-decoded-value-is-data)). Every dict of a document is read, one standing in a list included: an item has no layer below it, so it reads as a document merged over nothing, and a delete in it ends there (`_merge._as_list_item`, which refuses an item that is a delete itself). Until BUG-237 a list's items were skipped, so `rows: [{k: 4, k-: null}]` kept `k-` as a field, which construction refused, while the same item beside an `__include__` read it through the merge of the include's siblings.

List patches travel as a dict whose op keys are markers no channel types
([below](#no-channel-types-an-op)). These notes write a marker bare, `__append__`, and a plain
string key quoted, `'*'`:

| Op | Meaning | Produced by |
|---|---|---|
| `__append__` | append items | `--f+`, `F+`, `--config.<f>+`, `CONFIG__F+` |
| `__delete__` | delete original indices (before appends) | `--f.N-`, `F__N-` |
| `__base__` | replacement base list, or `DICT_DELETE`: no base at all | a whole-list value followed by a patch in the same source, or a deferred patch (an index past the base, or a key that is no index); `DICT_DELETE` when a whole-field delete is followed by an op at or below its path |
| `__delete_after__` | delete indices *after* appends | `--f.N-` appearing after `--f+` on the CLI |
| `"N"` | index patch (negative counts from the end) | `--f.N`, `F__N`, index-keyed dicts |

A file writes each of the four by the reserved key of the same name, which is how `dump_file`
writes one a merged dict still holds; nothing else writes them.

`_apply_list_ops` applies them in a **fixed semantic order** (pre-append deletes, appends,
post-append deletes, index patches) so the result never depends on dict iteration order.
`__base__` exists so a replacement followed by a patch in the same source is not lost when the
patch merges; `__delete_after__` exists so an index typed after an append refers to the
post-append list. An index patch recurses through `_merge_existing_value`, the one "combine
existing with override" dispatcher, so patches compose at any depth. The base and the indices
of either delete are each read by one function, `_replace_base` and `_delete_indices`, which
refuse a value of the wrong shape, as only a file can write one (BUG-170, BUG-175).

The value stored under `__append__` is always a list or a scalar (single-value append). Every
producer — `_read_file_ops` (a file's `__append__`, as written), `_merge_append_ops` (CLI `--f+`),
`_files._load_mount` (`--config.<f>+`, `CONFIG__F+`) and the `_merge_existing_value` combiner — stores one
of those two shapes. `_to_append_list` normalizes either to a flat list. An index-keyed
dict (`{"0": …, "1": …}`) is a *construct-time* concern — `typedload._construct` reads it
directly to build a sequence — not an append value, and the merge layer never produces one
under `__append__`. A dict branch that once accepted that shape there was speculative
("for future env-var support" that never arrived) and has been dropped; the environment
appends by a variable's name (FEAT-18), with the CLI's own writer, so it stores the same two shapes.

## No channel types an op

The four ops are the members of `confarg.ListOp`, an enum whose `str()` is the reserved key a file writes the op with, and which no string equals. A flag, a variable or a file can spell a dict key `*`, `+`, `-` or `~`, and even `__base__`; none of them spells a marker, so the merge cannot read a user's key as an op. The merged dict is typed `MergeDict` (`dict[str | ListOp, Any]`) along its whole path, so code that assumes a key is text fails the type checker rather than reading `__append__` as a field. Until FEAT-3 the ops were the plain strings `+`, `-`, `*` and `~`, and every channel could type them as a dict's keys: `--d.* 5` wiped the dict's other keys (BUG-185), `--d.* 1 2` and `--d.*-` still did once the merge told the two apart by the value (BUG-199), and of two files giving `d: {"+": 1}` and `d: {"+": 5}` the second appended where it meant to replace.

Only `_read_file_ops` makes a marker out of a string: a file's reserved key (`__append__`, `__delete__`, `__base__`, `__delete_after__`, listed in `_defaults.RESERVED_KEYS` beside the other [file-only keys](../config-files/reserved-keys.md#reserved-file-only-keys)). A flag, an environment variable or a mount point naming one is refused, by `_parse_cli._reserved_segment`, and so is a JSON value holding one, by `_cast.decode_json`, so the file is the one channel that writes an op by name. `_serialize_untyped` writes a marker back as that plain key, and a key delete as `{__unset__: true}` (BUG-202), so `dump_file(merge(...))` reads back, through `merge(files=[saved])`, as the merged dict it was, ops and deletes included.

A marker that reaches a dict field in `build()` (a file's `d: {__append__: …}`, or BUG-174's `--d.1-`) is refused by `_construct_dict` rather than built as one of the dict's keys. The plain string a direct `build()` caller might spell — out-of-contract, as no channel can produce it — is refused too. On a fixed tuple or a namedtuple, `_indexed_dict_to_positions` refuses it against a default, where `_resolve_tuple_partial`'s stray-skipping once dropped it silently, and without one alike, with one refusal naming the key (BUG-209); on a list, `_build_items`, which reads a list's index keys itself, refuses it as no integer index ([REF-94](../../todo/refactors/REF-94-construction-reads-a-sequences-index-keys-in-two-places.md)). A marker on a fixed tuple or a namedtuple applies over the `__base__` it carries, or, with none, is refused as on a dict, naming the op (`_construct._apply_carried_ops`, BUG-221): a fixed-arity sequence has no length an append could grow into. A default is that base too ([a field default is the base layer](../design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer)).

The alternatives weighed are in [design decisions](../design-decisions/merge-ops-are-markers-no-channel-types.md#merge-ops-are-markers-no-channel-types).

## Scalar intermediates

A path can reach a key whose parent already holds a scalar — `--d oops --d.c x`, or `D=oops`
beside `D__C=x`. There is nothing to descend into, so `_set_nested` replaces the scalar with
a fresh dict and the deeper key wins. That is not a new rule: `_deep_merge` already lets a
dict from a higher-precedence source replace a scalar from a lower one, the adapters' flat
collector already nests the subkey over the whole value, and the reverse order already lets
the whole value replace the subkeys. The crashing case was the only one that resolved to a
Python `TypeError` escaping the merge core instead of to last-write-wins.

The rule lives in one descent, `_descend_creating`, which every writer into a parse result
goes through — `_set_nested` and the list-index delete alike — and which opens each node with
`_open_for_ops`. The delete once carried a walk of its own that missed both the non-dict
replacement and the append-spec navigation, so it crashed on the sentinel a whole-field delete
leaves and recorded `--items+ … --items.-1.tags.0-` under a stray `'-1'` key (BUG-77). That
sentinel is *not* a scalar to replace: see the next section.

Replacing is right only because the scalar meant nothing to its field. Where it *does* mean
something — a bare string at a `Callable` field is the shorthand for `{bind: <string>}` — the
parsers open it into that meaning before `_set_nested` ever sees it, so the later key refines
it instead ([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)). `_set_nested` stays type-blind: the parsers already hold the type and open the scalar before it writes. The alternatives weighed — one blanket rule either way, or splitting by whether the scalar was meaningful — are in [design decisions](../design-decisions/whole-value-then-subkey.md#a-whole-value-followed-by-a-subkey-opens-rather-than-collides). Across layers, the merge opens it the same way, asking the same `_takes_callable_shorthand` ([above](#deep-merge-semantics)).

## An op after a whole-field delete has nothing below it

`--users- --users.0-` deletes the field, then index 0 of what is left: nothing, whatever the
lower layers held. Every op written after a whole-field delete — at or below its path, an index
set or delete, an append, a subfield, a whole dict — applies as it would with no file
setting the field at all:

| after `--users-`, file `users: [a, b]` | result | same as, with no file |
|---|---|---|
| `--users.0-` | error: requires a base list | `--users.0-` |
| `--users.0 x` | `[x]` | `--users.0 x` |
| `--users+ x` | `[x]` | `--users+ x` |
| `--sec.a 9`, `--sec '{"a": 9}'` (file `sec: {a: 5, b: 6}`) | `a=9`, `b` its default | `--sec.a 9` |

`_merge._open_for_ops` records it: a node holding `DICT_DELETE` opens into
`{__base__: DICT_DELETE}`, a base that is no base, and the ops are written beside it — by the one
descent, by the CLI's append (`_merge_append_ops`), and by `_merge._written_over` when a dict
value lands on the sentinel, from a flag, a variable, or the rest of a file's dict beside its
`__unset__` (a list or a scalar replaces the layers below on its own). A file writes the delete
and the ops after it in one value, `{__unset__: true, __append__: [x]}`, which applies the delete
first. Like a base list, the `__base__` discards whatever a lower layer holds at that path,
whichever layer — a file, the root `json` fold, the environment under the CLI — and the ops of
a higher layer refine it.
`_pipeline._merge_sources` drops the marker once every layer is merged
(`_merge._drop_deleted_bases`), so `merge()` hands `build()` the bare ops, the same dict a lone
op gives.

Until BUG-116 the sentinel was replaced like a scalar and the delete was silently lost:
`--users- --users.0-` built `[b]`. That was never decided. The pair crashed until BUG-23 added
the scalar branch to `_set_nested` for whole *values* left behind, which the sentinel fell into
(the index delete went on crashing on its own walk); BUG-77 then routed the index delete
through the same descent and wrote the side effect down as the rule. The alternatives weighed
are in
[design decisions](../design-decisions/an-op-after-a-whole-field-delete-applies-to-nothing-below.md#an-op-after-a-whole-field-delete-applies-to-nothing-below).

## A delete within one source deletes below it too

`--name-` deletes `name` in every layer below the CLI. Beside a root `--json` (or `<PREFIX>JSON` in the environment) it has to delete twice: in the decoded object, which the channel's fields refine, and in the files and channels below. `_deep_merge` cannot do both: it is the merge *between* layers, where the base is everything below, so it spends a delete on its base and drops it. Before BUG-186 the root fold used it, so the delete removed the object's `name`, never reached the files, and the file's value came back.

A file's document has parts too: what an `__include__` brings in, the keys written beside it, and the entries of an `__include__` list. Before BUG-227 they were merged with `_deep_merge` as well, so `{__include__: inc.yaml, name: {__unset__: true}}` or `__include__: [inc.yaml, del.yaml]` deleted `name` in `inc.yaml` and nowhere else, and so did a delete *in* the included part once any key stood beside it.

Two parts of one source are merged by `_merge._merge_within_source`, which `_cast.fold_root_json` calls, and `_files` for an include's siblings (`_include_with_siblings`) and for the entries of an `__include__` list (`_load_includes`): `_deep_merge`, then every key delete either part holds put back at its path (`_keep_deletes`), so the source's result still deletes in the layers it is merged over. The parts read as one flat document would:

- A delete of the override stays, whether or not the base held its key.
- A delete of the base stays where the override says nothing at its key. Where the override writes a value there, the value wins, as a later key does in one file; a dict written there keeps the delete as its `__base__`, cutting the layers below off (`_written_over`, [above](#an-op-after-a-whole-field-delete-has-nothing-below-it)). So `__include__: [delsec.yaml, secb.yaml]` builds what `{sec: {__unset__: true, b: 3}}` builds. A part that is itself a delete, a fragment holding `__unset__: true` alone, is written over the same way, by siblings and by later entries (`_merge._written_within_source`).
- A delete below a node the merge turned into a list, or that a union tag, a call or a cast pin replaced, is not put back, since that value replaces the layers below whole; nor is a list op's own `__base__` delete, which `_deep_merge` already keeps. A data entry (CSV/TSV) of an `__include__` list replaces the entries before it, deletes included.
- A list item has no layer below it at all, so `_files._resolve_node` drops whatever delete an include inside one kept for the layers below (`_merge._without_key_deletes`): `- {__include__: row.yaml, zz: {__unset__: true}}` builds the row, as it did before BUG-227, and as the same item written inline does ([above](#deep-merge-semantics)).

A delete put back that met a key of the base is put back *spent*, as a second instance of the sentinel, `_merge._SPENT_DELETE`. Every merge reads it as `DICT_DELETE` (`_deep_merge` tells a delete by `isinstance`), and `_drop_deleted_bases` drops one no layer below met once every layer is in. The plain sentinel is kept for a delete that found nothing in its own source, so `--json '{"data": {"x": 1}}' --data.x-` with no file builds `data={}` as before, while `--data.x-` alone still leaves the sentinel that a delete with no base leaves (BUG-98).

The same rule holds where a source writes its keys one by one rather than in parts: `_merge._spent_if_met` decides it for `_keep_deletes`, for an included delete written over an earlier part (`_written_within_source`) and for a flag's or a variable's delete (`_set_nested`). So `--data.x 1 --data.y 2 --data.x-` on argv builds `{y: 2}` with nothing below, as the include spelling does; until BUG-227 it left the plain sentinel and failed with BUG-98's error, and so did a file's `{x: 1, y: 2, x-: null}`, a spelling FEAT-43 made data. A spent delete is still a delete to every within-source writer: a dict or an append written over it cuts the layers below off as the plain one does (`_open_for_ops`). The alternatives weighed:

- **Put back the plain sentinel everywhere.** Rejected: the first spelling became BUG-98's error, though the decoded object had given the delete its base.
- **Drop every surviving delete silently**, as RFC 7396's JSON Merge Patch does with a `null` for an absent member. Rejected here because it decides, as a side effect, how a delete with no base in any layer ends, which is BUG-98's question and not this fold's.

Precedent: Helm coalesces chart values in stages and once lost a `null` (its delete) in an intermediate stage, so it never reached the defaults below. Its `chartutil` now keeps the `null` through the intermediate merge (`MergeValues`) and removes it only in the final one (`CoalesceValues`). `_merge_within_source` and `_drop_deleted_bases` split the work the same way.

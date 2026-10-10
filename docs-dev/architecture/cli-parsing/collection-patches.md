# Collection patch operations

| Syntax | Effect |
|---|---|
| `--f.N v`, `--f.-1 v` | replace element N (negative from the end) |
| `--f+ v…` | append ([design decisions](../design-decisions/plus-is-a-merge-operator.md#the--suffix-is-a-merge-operator-not-a-list-spelling)) |
| `--f.N-` | delete element N |
| `--f.key v` / `--f.key-` | set / delete a dict key |
| `--f.N.sub v` | patch inside an element |

They accumulate into the sentinel vocabulary of [pipeline](../pipeline/deep-merge.md#deep-merge-semantics)
in argv order. After `--f+ {}`, a negative index (`--f.-1.sub x`) navigates into the item
just appended (`_navigate_append_spec`), so repeated append-then-fill sequences each patch
their own new item.

A varlen `--f` is absent from the table because it is not a patch: it replaces the whole list,
and with no token at all it clears it — the other flag family that stands bare
([CLI adapters](../cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)). Repeating it extends the list it is building rather than
appending to the lower-priority sources, so it is still exactly one replacement however many
occurrences spell it; a plain occurrence therefore discards the patch ops recorded before it, which
is what makes `--f --f+ x` a reset followed by an append.

Three spellings therefore clear a list, and they are not interchangeable:

| Spelling | What it does |
|---|---|
| `--f a b` | replaces the lower-priority list outright — the ordinary "start over" |
| `--f` | replaces it with `[]` |
| `--f-` | drops the key, so the field falls back to its **default** rather than to `[]` |

`--f-` is the only one every front-end spells, because a delete registers value-less. It also ends
the list being built, so it resets the token accumulation: `--f x --f- --f a` is `['a']`, not
`['x', 'a']`. An *index* delete (`--f.1-`) is a patch inside the list and leaves the accumulation
alone. The adapters' CLI channel is this same loop over the same argv
([CLI adapters](../cli-adapters/model.md#argv-is-the-only-writer)), so there too
`--f x --f- --f a` is `['a']`.

`_is_collection_patch_path` answers "does this path index a list/tuple/set or key a dict?".
It is the dividing line between the flags a static walk can register and the ones the adapters
register only when argv types them
([CLI adapters](../cli-adapters/collection-patch-parity.md#collection-patch-parity)).

## A segment below a sequence is an index

Below a list, a set or a variadic tuple the walk (`_advance_field_type`) steps into the element
only on a segment that spells an index as `str()` writes one: `0`, `3`, `-1`, and not `01`,
`+1`, `-0` or `1_0`. It asks `dictexpr._expressions._list_index`, the one answer to "does this
segment spell a list index?" that a `${xs.0}` reference already reads by (BUG-133), and the
one the namedtuple's generated spellings agree with (BUG-97). Any other segment is no path:
the loop refuses `--xs.foo 5` as unknown, and `--xs. 5` as a missing name, as it refuses
`--sub.` (BUG-170).

The reason is the merge vocabulary, not tidiness. A patch below a sequence travels as a dict
whose keys the merge reads as indices, beside its own ops
([pipeline](../pipeline/deep-merge.md#deep-merge-semantics)), so a user's segment stored there
has to be an index for anything to read it. The walk once stepped into the element whatever the
segment spelled, and while the ops were the plain strings `+`, `-`, `*`, `~` (until FEAT-3),
`--xs.+ 1` appended and `--xs.* 5` crashed `build()` with a raw `TypeError`. Refusing at the
walk is what lets registration and the loop agree, since both ask it. RFC 6901 (JSON
Pointer) draws the same line for an array index: digits, no leading zero.

The same holds wherever leniency would otherwise store the segment. Below a dict a path the
walk refuses is a key path, left to `build()` (BUG-161) — except when the branch refuses it
standing on a sequence, which `_refuses_at_a_sequence` names and `_is_dict_at_path` excludes:
`--d.k.* 5` on a `dict[str, list[int]]` addresses the list, not a key of the dict. Fixed
tuples and namedtuples count as sequences there, since the merge carries their patches in
the same `__base__` shape. The environment, which leaves any other unknown path below its first
segment to `build()`, refuses such a variable at parse through `_sequence_refusal`
([environment parsing](../environment-parsing.md#environment-parsing)).

Configuration files are not walked, so a file key below a list is still read by the merge's
`int()`: `xs: {"01": 5}` patches index 1. Only a file writes a list op by name
(`__base__`, `__append__`, ...), which no other channel may
([reserved keys](../config-files/reserved-keys.md#reserved-file-only-keys)), and the one reader
of each op that holds a list, `_merge._replace_base` for the base and `_merge._delete_indices`
for either delete, refuses a value of the wrong shape rather than reading it with `list()` or
iterating it (BUG-170, BUG-175).

## An append reaches every sequence variant

`--xs+` appends wherever a branch of the walk holds a list, a set or a variadic tuple at the flag's path, each union spread into its variants (`_append_element_type`, asked of `_field_types`). It once asked the folded type alone whether it was a list, and a union is none, so `list[int] | None` and `list[int] | str` refused `--xs+` while taking `--xs.0`, `--xs.0-` and a file's `xs+:` (D4, found fixing BUG-221). The question is the one `--xs.<i>` already answers per branch, the way a cast is checked against each branch rather than their fold (BUG-214). The items are coerced by the fold of the variants' element types (`_common_type`): their common type, or the raw token where they disagree, which construction reads by the variant it picks. A field with no such variant — a leaf, `Any`, a fixed tuple, a namedtuple — is still refused with the "not a list, set, or frozenset" message.

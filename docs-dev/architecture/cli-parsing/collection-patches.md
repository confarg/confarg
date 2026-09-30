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
alone. The adapters honor the same order: their scan erases the ops a plain occurrence supersedes
([CLI adapters](../cli-adapters/collection-patch-parity.md#a-plain-occurrence-erases-the-ops-before-it)), so there too
`--f- --f a` is `['a']`, and their collector drops the pre-delete tokens the frameworks
accumulated into one value
([CLI adapters](../cli-adapters/collection-patch-parity.md#a-whole-field-delete-ends-the-token-accumulation)),
so there too `--f x --f- --f a` is `['a']`.

`_is_collection_patch_path` answers "does this path index a list/tuple/set or key a dict?".
It is the dividing line between what a framework's flat parse result can represent and what
needs the argv-order patch scan ([CLI adapters](../cli-adapters/collection-patch-parity.md#collection-patch-parity)).

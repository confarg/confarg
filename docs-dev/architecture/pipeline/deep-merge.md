# Deep merge

## Deep merge semantics

`_merge._deep_merge(base, override)` is recursive, **dict-wins**: the override replaces
anything that is not a dict-on-dict, which is merged recursively.

- **A union tag in the override discards the base entirely.** Naming a class says "this is
  a new object", so fields of the previous variant must not leak in (the README's
  `--class myapp.SQLiteConfig --dbpath …` over a server config).
- **A base list carried with its patch discards a dict base.** An override holding `"*"`
  is "this list, then these patches", so it replaces a name dict or an earlier deferred patch
  rather than merging into it
  ([design decisions](../design-decisions/namedtuple-arity-flag-argv-order.md#a-base-list-carried-with-its-patch-replaces-what-lay-below)).
  A `"*"` holding `DICT_DELETE` discards a list base too: it is a whole-field delete with
  ops after it ([below](#an-op-after-a-whole-field-delete-has-nothing-below-it)).
- `DICT_DELETE` (from `key-` in files, `--field.key-`, `FOO__KEY-`) removes a key.
- File-sourced shorthand `key+:` / `key-:` / `"N-":` is normalized to sentinels by
  `_normalize_merge_ops` so files, env and CLI share one patch vocabulary.

List patches travel as a dict of sentinel keys:

| Key | Meaning | Produced by |
|---|---|---|
| `"+"` | append items | `--f+`, `key+:`, `--config.<f>+` |
| `"-"` | delete original indices (before appends) | `--f.N-`, `"N-":`, `F__N-` |
| `"*"` | replacement base list, or `DICT_DELETE`: no base at all | a whole-list value followed by a patch in the same source, or a deferred patch (an index past the base, or a key that is no index); `DICT_DELETE` when a whole-field delete is followed by an op at or below its path |
| `"~"` | delete indices *after* appends | `--f.N-` appearing after `--f+` on the CLI |
| `"N"` | index patch (negative counts from the end) | `--f.N`, `F__N`, index-keyed dicts |

`_apply_list_ops` applies them in a **fixed semantic order** (pre-append deletes, appends,
post-append deletes, index patches) so the result never depends on dict iteration order.
`"*"` exists so a replacement followed by a patch in the same source is not lost when the
patch merges; `"~"` exists so an index typed after an append refers to the post-append list.
An index patch recurses through `_merge_existing_value`, the one "combine existing with
override" dispatcher, so patches compose at any depth.

The value stored under `"+"` is always a list or a scalar (single-value append). Every
producer — `_apply_append_key` (file `key+:`), `_merge_append_ops` (CLI `--f+`),
`_load_cli_config` (`--config.<f>+`) and the `_merge_existing_value` combiner — stores one
of those two shapes. `_to_append_list` normalizes either to a flat list. An index-keyed
dict (`{"0": …, "1": …}`) is a *construct-time* concern — `typedload._construct` reads it
directly to build a sequence — not an append value, and the merge layer never produces one
under `"+"`. A dict branch that once accepted that shape under `"+"` was speculative
("for future env-var support" that never arrived) and has been dropped; env has no append
concept, so there is no path that could reach it.

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
something — a bare string at a `Callable` field is the shorthand for `{fn: <string>}` — the
parsers open it into that meaning before `_set_nested` ever sees it, so the later key refines
it instead ([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)). `_set_nested` stays type-blind: it is
merge-layer code, and asking it which scalars are meaningful would put type knowledge behind
the [merge/build contract](merge-build-contract.md#merge-build-contract). The alternatives weighed — one blanket
rule either way, or splitting by whether the scalar was meaningful — are in
[design decisions](../design-decisions/whole-value-then-subkey.md#a-whole-value-followed-by-a-subkey-opens-rather-than-collides).

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
`{'*': DICT_DELETE}`, a base that is no base, and the ops are written beside it — by the one
descent, by the CLI's append (`_merge_append_ops`), by a file's `key+:` written after its
`key-:` (`_apply_append_key`), and by `_merge._written_over` when a dict value lands on the
sentinel, from a flag, a variable or a file's later `key:` (a list or a scalar replaces the
layers below on its own). The file channel takes its keys in document order, as the CLI takes
argv. Like a base list, the `"*"` discards whatever a lower layer holds at that path,
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

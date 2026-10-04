# Deep merge

## Deep merge semantics

`_merge._deep_merge(base, override)` is recursive, **dict-wins**: the override replaces
anything that is not a dict-on-dict, which is merged recursively.

- **A union tag in the override discards the base entirely.** Naming a class says "this is
  a new object", so fields of the previous variant must not leak in (the README's
  `--class myapp.SQLiteConfig --dbpath …` over a server config).
- `DICT_DELETE` (from `key-` in files, `--field.key-`, `FOO__KEY-`) removes a key.
- File-sourced shorthand `key+:` / `key-:` / `"N-":` is normalized to sentinels by
  `_normalize_merge_ops` so files, env and CLI share one patch vocabulary.

List patches travel as a dict of sentinel keys:

| Key | Meaning | Produced by |
|---|---|---|
| `"+"` | append items | `--f+`, `key+:`, `--config.<f>+` |
| `"-"` | delete original indices (before appends) | `--f.N-`, `"N-":`, `F__N-` |
| `"*"` | replacement base list | a whole-list value followed by a patch in the same source, or a deferred index patch |
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

The same holds for the sentinel a whole-field delete leaves: `--users- --users.0-` is an
index delete written after it, and records like a lone `--users.0-`. The rule lives in one
descent, `_descend_creating`, which every writer into a parse result goes through —
`_set_nested` and the list-index delete alike. The delete once carried a walk of its own
that missed both the non-dict replacement and the append-spec navigation, so it crashed on
the sentinel and recorded `--items+ … --items.-1.tags.0-` under a stray `'-1'` key (BUG-77).

Replacing is right only because the scalar meant nothing to its field. Where it *does* mean
something — a bare string at a `Callable` field is the shorthand for `{fn: <string>}` — the
parsers open it into that meaning before `_set_nested` ever sees it, so the later key refines
it instead ([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)). `_set_nested` stays type-blind: it is
merge-layer code, and asking it which scalars are meaningful would put type knowledge behind
the [merge/build contract](merge-build-contract.md#merge-build-contract). The alternatives weighed — one blanket
rule either way, or splitting by whether the scalar was meaningful — are in
[design decisions](../design-decisions/whole-value-then-subkey.md#a-whole-value-followed-by-a-subkey-opens-rather-than-collides).

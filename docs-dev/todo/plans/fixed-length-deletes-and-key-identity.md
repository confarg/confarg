# Fixed-length deletes and key identity

The plan for [BUG-243](../bugs/BUG-243-a-delete-on-a-fixed-length-sequence-has-no-settled-meaning.md) and BUG-244 (closed by step 2, whose rationale is in [which keys are one key](../../architecture/pipeline/deep-merge.md#which-keys-are-one-key)), with BUG-108, BUG-142 and Q-1 folded in (closed by step 1, whose rationale is in [a position is one key](../../architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-position-is-one-key-whatever-spells-it)). Every decision below was settled with the maintainer on 2026-10-15; the examples are the agreed outcomes.

## One question underneath

Both bugs ask which keys are the same key, and what a delete does to a position that cannot shift. The type the merge stands at (`MergeAt`, typed by `_typed_merge.TypedAt`) answers both.

## Decisions

### Key identity (BUG-244, Q-1)

1. **By the type.** At a `dict[K, V]`, two keys are one key when they coerce to the same `K` (construction's own key coercion). A key that does not coerce matches by equality only, and construction refuses it as before. `{1: 5}` from YAML with `--d.1-` builds `{}`; with `--d.1 9`, one key holding 9; `dict[Color, int]`'s `RED` and `1` (RED's value) are one key.
2. **At a fixed-length node** (namedtuple, fixed tuple), a position is one key whatever spells it: a namedtuple's field name, its index `str(i)`, its negative index `str(i - n)`, a YAML integer key. Only those spellings name a position, in every channel and at every stage (BUG-108, BUG-142): `01`, `+1`, `-0` are refused on a fixed tuple and a namedtuple alike, a file included. A plain list keeps its own rule (REF-94).
3. **On an untyped node** (`Any`, a bare `dict`, `dict[Any, V]`, an unannotated argument), a string key meets a non-string key only when it is JSON's spelling of that key, `json.dumps(k)` without the quotes: `1` → `"1"`, `True` → `"true"`, `None` → `"null"`, `1.5` → `"1.5"`. A key JSON cannot write (a date) matches by equality. `--a.True 9` over YAML `{true: 5}` stays a second key; `--a.true 9` meets it.
4. **A union** uses its branches' identity where every branch that can hold the node agrees on it, a single non-`None` variant included; otherwise the untyped rule. A tag that names a struct variant narrows the node as the typed merge already does.
5. **The base's key is kept.** When two spellings meet, the merged dict keeps the lower layer's key object and its position; the override's value merges in. `merge()` stays as written: no coerced key is stored.
6. **Everywhere keys are matched.** The merge between layers, the writers within one source (`_set_nested`, `_merge_within_source`, `_spent_if_met`), the default layer and construction ask the one identity. Within one source a later spelling of a key writes over the earlier one in place, and a later delete meets it.
7. **Construction reconciles a mixed namedtuple dict** (Q-1): two spellings of one position in one dict, which only one source can produce, resolve in dict order, the later write winning. `--pt.0- --pt.y 5` builds `Pt(1, 5)`; `--pt.x 13 --pt.0 9` builds `Pt(9, 2)`.

### A delete on a fixed-length position (BUG-243)

8. **It unsets the position; nothing slides.** A namedtuple field falls back to its class default, or is a missing field; a fixed tuple's position is `None` where its type takes `None`, else a missing field. With `Pt(x=1, y=2)` defaults and a file's `pt: [7, 8]`: `--pt.0-`, `--pt.x-` and `--pt.-2-` build `Pt(1, 8)`; `--rq.x- --rq.x 1` builds `Req(1, 8)`; `t: tuple[int, int]` with `--t.0-` is `MissingFieldError` at `t.0`, `to: tuple[int | None, int]` builds `(None, 8)`.
9. **It removes the position from the field default too.** `pt: Pt = Pt(5, 6)` with `--pt.x-` builds `Pt(1, 6)`, and over a file's `[7, 8]` `Pt(1, 8)`.
10. **Argv and the environment write it as a key delete** at the key as spelled. `_parse_cli._delete_index` counts a fixed-length node among the keyed kinds: a union takes the key delete only where every branch is a dict, a struct or fixed-length; any list, set or variadic tuple branch keeps the index delete (Q-8 stays open).
11. **A file's `__delete__` and `__delete_after__` are refused** on a fixed-length node, pointing at `{__unset__: true}` at the position. `__append__` over a base still applies and is checked against the arity. FEAT-43's refusal of `"N": {__unset__: true}` stays for a list and is lifted for a fixed-length node.
12. **Over a base list, the base becomes its keyed form, the delete kept in it**: the namedtuple by field name, the fixed tuple by index, `pt: {y: 8, x: DEL}`, dumped as `pt: {y: 8, x: {__unset__: true}}`. At a fixed-length node `_deep_merge` keeps a delete the base holds, where it drops one elsewhere; a later write at the same position replaces it. The default layer consumes it: it removes the position from the default it lays, then drops it, so construction never meets it.
13. **A reference reads the built value.** `${pt.x}` is what `pt.x` builds to. The default layer and construction ask one function what an unset position holds, so the two cannot drift.

## Rejected

- **Refusing a fixed-length delete at parse**: a file already spells `pt: {x: {__unset__: true}}`, and a struct field's `--sub.p-` already falls back to the class default.
- **The field default per position** (`--t.0-` builds `(1, 8)`): a delete would mean something else once a file is involved, and a fixed tuple has no per-position default of its own.
- **Deferring the delete beside its base** (`{__base__: [7, 8], x: DEL}`): `_deep_merge` drops a base's delete when a higher layer merges over it, so env `APP_PT__X-` under argv `--pt.y 5` lost it.
- **Dropping the delete once it met the base list** (`{y: 8}`): the default layer then lays the field default under it, as under any patch, and `Pt(5, 6)` would show through.
- **Identity by spelling, `str(key)`**: misses `true`/`True`, `RED`/`1`, `1.0`/`1`.
- **Storing the coerced key**: `merge()` would hold `Color.RED`, which no writer spells.
- **YAML's spelling for the untyped rule**: it differs from JSON's only for `1.0e+20` and `.inf`, and JSON is the string-keyed format the other channels share.

## Build order

1. **Canonical position** (BUG-108, BUG-142, Q-1), landed: one reader of "which position does this key name?" for a fixed-length type, asked by the walk, `_indexed_dict_to_positions`, `_construct_namedtuple` and the default layer; construction reconciles a mixed dict in order.
2. **Key identity** (BUG-244), landed: `MergeAt` answers a key's identity; `_deep_merge`, the within-source writers and `_set_nested` (given the parse's typed root) match by it.
3. **Position delete** (BUG-243): the delete decoder, the keyed form with its kept delete, the `__delete__` refusal, the default layer's consumption, and construction's unset position.

Each step lands as its own revision, test-first.

## Done when

The reproductions of the four bugs build as above in every channel and front-end, the backend contract suite covers the argv spellings, Q-1's and the bugs' tickets are deleted, and the decisions above live in `docs-dev/architecture/` (deep merge, collection patches, the namedtuple and default-layer design decisions, limitations) with this file deleted.

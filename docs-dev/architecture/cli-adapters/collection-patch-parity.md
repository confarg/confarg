# Collection patch parity

Frameworks own whole-field values (so click keeps its repeated-flag list syntax), but their
parse results cannot express argv-ordered, interleaved patches such as
`--dbs+ {} --dbs.-1.dbpath db1 --dbs+ {} --dbs.-1.dbpath db2`. The two halves:

1. `build_dynamic_flags` registers exactly the patch flags present in argv (value-less for
   deletes) so the framework accepts them;
2. `merge_*` re-runs the vanilla parse loop in `patch_only=True` mode over **argv** (not the
   framework result), which skips everything the flat collector owns and applies patch ops in
   command order, then deep-merges them over the collected values.

Argv (not the namespace) is also what preserves the left-to-right order of interleaved
`--config[.subpath]` flags. Both halves route the decision through `_is_replayed_path`: a
collection patch (`_is_collection_patch_path`, so `--input.1.str yes`, a cast on an element,
is a patch), or a union tag the walk reaches by its fallback
([a tag is a replayed write](#a-tag-is-a-replayed-write)).

History: patches, dict subkeys, bind-on-`__call__` and expressions over CLI numbers were
vanilla-only until PR #72.

One family of patch flags needs more than registering: a patch flag that may legally carry no
token at all, whose occurrence a framework cannot be handed as typed —
[a flag that stands bare](a-flag-that-stands-bare.md#a-flag-that-stands-bare).

A value-less delete also repeats — a delete spelled twice is the same delete, and the
whole-field one is idempotent anyway. Every front-end but cyclopts takes the repeat in
stride; a value-less cyclopts parameter refuses the second occurrence with a usage error,
where its plain flags repeat (`consume_multiple`) and its appends accumulate. Nothing needs
the argv-dropping the stands-bare family built: a delete's value never reaches a parse
result the collector reads, because the patch scan reads argv, so the registration itself
tells cyclopts to allow the repeat (`allow_repeating=True`) and cyclopts keeps only the
last occurrence — indistinguishable from the first for a flag with no value (BUG-78).

## A patch op joins the values the framework collected

Splitting one channel across two dicts costs what vanilla gets for free by writing both into
a single `ctx.data`: each half has to be told about the other, or the merge that rejoins them
reads them as two priorities rather than one. Two things follow, both settled by BUG-24.

**The patch scan is handed the collected dict** (`_parse_cli(..., patch_base=…)`). Vanilla
opens a bare-string callable shorthand before it stores a flag below it, through the one
`_open_callable_shorthand` every channel calls
([callables](../callables.md#cli)); in `patch_only` mode the scan's own dict is empty, because
`--fn pkg.func` belongs to the flat collector, so the opener saw nothing and the deep merge
replaced the scalar instead of refining it. Passing the collected dict in puts the shorthand
where the canonical opener can see it, at the same point in the same loop — rather than
teaching `cli/_collect.py` a second answer to a question `_parse_cli` already answers.

**A delete is re-asserted after the merge** (`_collect._restore_patch_deletes`). Inside one
channel `--<field>.<key>-` is a *record*, not an operation: vanilla stores the sentinel and
leaves `_merge_sources` to apply it against the lower-priority sources. `_deep_merge` applies
it on sight, which is right for its usual job of joining two priorities and wrong here, so
the sentinels the patch scan recorded are written back over the merged dict. Without that,
`--fn.fn X --fn.bind-` silently kept a config file's `bind` that vanilla deletes. Only
dict-key deletes carry a sentinel; a list index delete travels as an index list under
`"-"`/`"~"`, and with no collected list at its path it *is* an operation the merge
applies against the lower-priority sources, exactly as vanilla applies it — a collected
list under it is the one case that records instead
([a patch op records against a list the channel collected](#a-patch-op-records-against-a-list-the-channel-collected)).

Re-asserting means the delete wins wherever both spellings touch one key — but only for a
delete that *survives the argv-order replay*: a plain flag the scan skips erases the ops
recorded before it
([a plain occurrence erases the ops before it](#a-plain-occurrence-erases-the-ops-before-it)).

## A patch op records against a list the channel collected

The delete rule above generalizes: within one channel, *every* list op is a record, not an
application. Vanilla writes a plain occurrence and the patch after it into one `ctx.data`,
and its own descent — `_set_nested`'s intermediate promotion, `_accumulate_list_delete`'s
walk, `_merge_append_ops` — turns the stored list into the `'*'` base and records the op
beside it, for `build()` to apply: `--users a --users.0-` holds
`{'users': {'*': ['a'], '-': [0]}}`, and a fixed tuple's `--pair 1 2 --pair.0 5` holds
`{'pair': {'*': [1, 2], '0': 5}}`.

The adapters' join deep-merges the scan's ops over the collected values, and
`_deep_merge` applies list ops on sight (`_merge_list_base` → `_apply_list_ops`) — right
for its usual job of joining two priorities, wrong within one channel. The applied shape
built the same object, but the merged dict was not byte-identical, and it read as one
priority too many: the base list had become the op's private operand (BUG-67).

So the join's list-op half is repaired before it, as the delete half is repaired after it:
`cli/_collect._promote_patched_lists` walks the scan's op tree in step with the collected
dict and promotes every plain list an op dict addresses into `{'*': list}`, and the deep
merge that follows only lays the op keys beside the base. The promotion is unconditional —
any op dict over a collected list takes the recorded shape, whatever op kind it holds —
because vanilla's descent promotes unconditionally too. A lower-priority source still
sees the applied result: `_merge_list_base` applies a `'*'`-bearing dict on sight, so
`{'*': [1, 2], '0': 5}` over a config file's list is `[5, 2]`, on both sides of the seam.

A namedtuple's positional run is the one list that promotes differently, because vanilla's
descent promotes it differently: its positions are its fields, so
`_parse_cli._promote_namedtuple_positional` re-keys it by field name (BUG-66).
`_promote_patched_lists` calls that same function for every path an op addresses before it
does the `'*'` promotion. So `--pt 1 2 --pt.class X` merges as
`{'pt': {'x': 1, 'y': 2, 'class': 'X'}}` on every front-end. An arity flag typed *after* the
op erases the op ([below](#a-plain-occurrence-erases-the-ops-before-it)), so nothing addresses
the run and it stays the list it was.

## A tag is a replayed write

Vanilla's tag rule answers the tag segment whatever the parent: `--leaf.class X` on an `int`
field, `--pt.class X` on a namedtuple, `--v.class X` on a scalar root all merge as
`{<path>: {'class': 'X'}}`, and `build()` judges the result. The question "is this segment the
tag?" is the walk's own: `_parse_cli._names_tag_by_fallback` holds when the path resolves with
the tag rule and does not without it (`_resolve_field_type(..., tag_fallback=False)`). A member
spelled like the tag, such as a field, a subclass-only field or a callable's directive, never
passes.

Such a tag is written by the patch scan, like a collection patch. Registration and the scan
both ask `_is_replayed_path`, so the frameworks accept exactly the tags the scan writes, and
the scan writes them in argv order. `--leaf 5 --leaf.class X` is the tag, and
`--leaf.class X --leaf 5` is `5`, for the same reason any later plain write erases the ops
before it. At a struct-shaped parent the collector's tag branches also write the tag (they
need it to choose a subclass to descend into). The two writes carry the same value, and the
replayed one lands last, as vanilla's own write does. The flag is registered only when typed,
on the help-noise ground of the other dynamic flags
([static and dynamic flags](static-and-dynamic-flags.md#static-and-dynamic-flags)).

Rejected: the argv scan BUG-92 first added, which registered the tag only at a struct path the
static walk had given none. It decided admission with its own rule ("a struct parent, no struct
subclasses, tag not shadowed") instead of asking the walk. That rule copied the static walk's
registration decision, and it left the non-struct parents refused at parse time (BUG-106).
The refusal had to stay because no collector branch wrote a tag there, so accepting the flag
would have dropped its value. Routing every tag through the replay removes that reason: the
writer is vanilla's own loop, wherever the walk reaches the tag.

## A plain occurrence erases the ops before it

Vanilla writes plain values and patch ops into one `ctx.data` in argv order, so a plain
occurrence replaces the node at its path and every earlier op at that path or below dies
with it. The scan sees the same argv but *skips* the plain occurrences (they belong to the
flat collector), and a skip that wrote nothing would let the ops recorded before it win the
deep merge — a delete anywhere in argv beating a value anywhere in argv (BUG-53), an append
before a plain occurrence surviving it (BUG-54).

So the skip replays the write's destructive half: `_pop_nested(ctx.data, path)`, at both skip
sites (plain field and plain force-cast). Only the erase, not the value — the value comes
from the flat collector via the merge, and the surviving ops (those after the last plain
occurrence above them) apply over it exactly as vanilla applies them over the plain write.
The erase descends like `_set_nested` and stops at the first non-dict intermediate, popping
it: a delete sentinel on the way down is replaced wholesale by the write that follows, so it
dies too, as it does in vanilla (`--db- --db.host x` keeps only the `host` write).

## A whole-field delete ends the token accumulation

Vanilla's whole-field delete pops the token accumulation at its path, so `--f x --f- --f a`
is `['a']` — the occurrence after the delete starts a new list
([collection patches](../cli-parsing/collection-patches.md#collection-patch-operations)).
The flat collector cannot see that on its own: the repeated-flag convention hands it every
plain occurrence's tokens in one list
([list syntax](list-syntax-divergence.md#list-syntax-divergence)), so the tokens spelled
before the delete survive *inside* the value of the occurrence after it. Nor can the patch
scan settle it, because the delete the scan records is popped by the very plain occurrence
whose value spans it — the order is real in argv and invisible in both halves (BUG-76).

The collector therefore reads the occurrence runs off argv itself
(`cli/_collect._tokens_past_whole_field_delete`, the reader shape of
`_fixed_arity_occurrence_runs`), keeping only the tokens of the runs that follow the last
whole-field delete at the path — and only when the flat value's length adds up to the runs
argv spells, so a value argv cannot account for is left to the shapers as it arrived. The
two call sites are the two shapes whose flags accumulate tokens: a varlen collection's leaf
branch, and a union's `_collect_union_seq_value`. A bare occurrence after the delete is a
run of its own — an empty one — so the clear it spells survives the same read, where before
the fix the flat value kept the pre-delete tokens of an occurrence the delete had ended.

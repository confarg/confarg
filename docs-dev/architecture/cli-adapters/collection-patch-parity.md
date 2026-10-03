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
`--config[.subpath]` flags. Both halves route the decision through
`_is_collection_patch_path` (so `--input.1.str yes`, a cast on an element, is a patch).

History: patches, dict subkeys, bind-on-`__call__` and expressions over CLI numbers were
vanilla-only until PR #72.

One family of patch flags needs more than registering: a patch flag that may legally carry no
token at all, whose occurrence a framework cannot be handed as typed —
[a flag that stands bare](a-flag-that-stands-bare.md#a-flag-that-stands-bare).

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
`"-"`/`"~"` and *is* an operation the merge applies, exactly as vanilla applies it.

Re-asserting means the delete wins wherever both spellings touch one key — but only for a
delete that *survives the argv-order replay*: a plain flag the scan skips erases the ops
recorded before it
([a plain occurrence erases the ops before it](#a-plain-occurrence-erases-the-ops-before-it)).

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

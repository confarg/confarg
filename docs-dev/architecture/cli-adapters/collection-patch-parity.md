# Collection patch parity

Frameworks own whole-field spellings (so click keeps its repeated-flag list syntax), but no
static walk can list the flags of an open-ended path: argv-ordered, interleaved patches such as
`--dbs+ {} --dbs.-1.dbpath db1 --dbs+ {} --dbs.-1.dbpath db2` name list indices, appends,
deletes and dict keys only argv knows. `build_dynamic_flags` therefore registers exactly the
patch flags present in argv (value-less for deletes), so the framework accepts them. What they
write is not the framework's to say: the adapters' CLI channel is vanilla's loop over argv
([argv is the only writer](model.md#argv-is-the-only-writer)), which applies every patch in
command order exactly as vanilla does.

Registration asks `_parse_cli._registered_when_typed`: a collection patch
(`_is_collection_patch_path`, so `--input.1.str yes`, a cast on an element, is a patch), or a
union tag the walk reaches by its fallback ([a tag is a replayed write](#a-tag-is-a-replayed-write)).

History: patches, dict subkeys, bind-on-`__call__` and expressions over CLI numbers were
vanilla-only until PR #72.

One family of patch flags needs more than registering: a patch flag that may legally carry no
token at all, whose occurrence a framework cannot be handed as typed —
[a flag that stands bare](a-flag-that-stands-bare.md#a-flag-that-stands-bare).

A value-less delete also repeats — a delete spelled twice is the same delete, and the
whole-field one is idempotent anyway. Every front-end but cyclopts takes the repeat in
stride; a value-less cyclopts parameter refuses the second occurrence with a usage error,
where its plain flags repeat (`consume_multiple`) and its appends accumulate. Since a delete's
value is read off argv, never off the parse result, the registration itself tells cyclopts to
allow the repeat (`allow_repeating=True`) and cyclopts keeps only the last occurrence —
indistinguishable from the first for a flag with no value (BUG-78).

## A tag is a replayed write

Vanilla's tag rule answers the tag segment whatever the parent: `--leaf.class X` on an `int`
field, `--pt.class X` on a namedtuple, `--v.class X` on a scalar root all merge as
`{<path>: {'class': 'X'}}`, and `build()` judges the result. The question "is this segment the
tag?" is the walk's own: `_parse_cli._names_tag_by_fallback` holds when the path resolves with
the tag rule and does not without it (`_resolve_field_type(..., tag_fallback=False)`). A member
spelled like the tag, such as a field, a subclass-only field or a callable's directive, never
passes.

Such a tag is registered like a collection patch, only when typed, on the help-noise ground of
the other dynamic flags
([static and dynamic flags](static-and-dynamic-flags.md#static-and-dynamic-flags)), and written
by the loop in argv order: `--leaf 5 --leaf.class X` is the tag, and `--leaf.class X --leaf 5`
is `5`.

Rejected: the argv scan BUG-92 first added, which registered the tag only at a struct path the
static walk had given none. It decided admission with its own rule ("a struct parent, no struct
subclasses, tag not shadowed") instead of asking the walk. That rule copied the static walk's
registration decision, and it left the non-struct parents refused at parse time (BUG-106).
The refusal had to stay because no collector branch wrote a tag there, so accepting the flag
would have dropped its value. Routing every tag through vanilla's loop removed that reason.

## Superseded: two halves joined by a merge

Until REF-72 the adapters built the CLI channel in two halves: a flat collector walked the
target type over the framework's parse result, and the loop ran in a `patch_only` mode for
patches alone, its ops deep-merged over the collected values. Splitting one channel across two
dicts cost what vanilla gets for free by writing both into one `ctx.data`, and each cost was
paid with a repair:

- the scan was handed the collected dict (`patch_base`), so a bare callable shorthand the
  collector stored was opened before a patch below it (BUG-24);
- a delete was re-asserted after the merge (`_restore_patch_deletes`), because `_deep_merge`
  applies a delete sentinel on sight where within one channel it is a record;
- a collected list an op addressed was promoted into the `'*'` base first
  (`_promote_patched_lists`), because `_deep_merge` applies list ops on sight too (BUG-67);
- a skipped plain flag replayed its write's destructive half (`_pop_nested`), so the ops before
  it died with the node, as in vanilla (BUG-53, BUG-54);
- a whole-field delete between two occurrences of a repeated flag was read back off argv
  (`_tokens_past_whole_field_delete`), because the parse result folds every occurrence's
  tokens into one value (BUG-76).

Each repair recovered one piece of vanilla's sequential loop, and each modeled less than the
loop. With the loop as the only writer, all of them are the loop's own behavior
([collection patches](../cli-parsing/collection-patches.md#collection-patch-operations)).

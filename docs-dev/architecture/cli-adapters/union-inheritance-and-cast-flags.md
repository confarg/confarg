# Union, inheritance and cast flags

- A struct union registers `--f.<union_tag>` plus the fields of every variant. Same-named
  flags from different variants are merged and their `choices` unioned
  (`_merge_or_append_spec`): first-wins would drop the other variants' values.
- A base class with subclasses registers the tag and all subclass fields (recursively for
  completion paths). "Has subclasses" means *imported* subclasses, so the class a tag names on
  argv or in a `--config` file is imported first, by `_tags.import_tagged_classes`
  ([design decisions](../design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration)); without that the
  selector and the subclass's own flags exist or not depending on which modules happened to
  load. The completer is left unset when the subclass list
  is empty — an empty one suppresses the shell's own suggestions.

  Registration and collection read the *same* answer: `merge_*` runs `_tags.collect_tags` over
  the stripped argv and hands the resulting `{field path: class path}` map to
  `_collect_ns_fields`, so the flat collector descends into the subclass a `--config` file names
  exactly as it descends into one a `--<path>.<union_tag>` flag names. Reading the tag from the
  flat parse result alone left a subclass field typed on the CLI with no type to hang on, and it
  was dropped while vanilla kept it. Only a tag found in
  *flat* is written back into the collected dict: a file's tag already reaches the merge at its
  own priority, and re-emitting it at CLI priority would replace the file's plain string with a
  `_StrToken` and break [byte-identical merged dicts](parity.md#byte-identical-merged-dicts).
  The write-back happens *before* the tag's import resolves, and through one shared step —
  `_collect._collect_named_variant` resolving with `_collect._tag_named_struct` — for the
  union-field and the inheritance branch alike; the argparse completion pre-extend resolves its
  tags through the same `_tag_named_struct`. Writing the tag only after a successful import (the
  inheritance branch's old shape) dropped a tag whose import failed, while vanilla keeps
  `--<path>.<union_tag>` as a raw string and lets `construct()` raise the import error naming the
  bad path — so the tag must survive collection byte-identically, or the user hears a
  "no discriminator was provided" complaint about a discriminator they did provide (BUG-45).
- A path whose type shows no subclass accepts the tag too, and so does any other path the
  walk reaches the tag at: a struct with no subclasses, a leaf field, a namedtuple, a
  scalar root. Vanilla's tag rule answers the segment whatever the parent, and `build()`
  raises its own complaint for a class path that selects nothing. The static walk registers
  the tag only where it can see subclasses. Everywhere else the tag is a replayed write: it
  is registered when typed and written by the patch scan in argv order
  ([a tag is a replayed write](collection-patch-parity.md#a-tag-is-a-replayed-write);
  BUG-92, BUG-106).
- With a tag present, the collector descends into the **other** variants at the path too, not
  only the named one: the union's remaining struct variants, or the base's remaining subclasses
  (`_dataclass_subclasses`, the same set vanilla's `_subclass_field_type` searches). Vanilla
  keeps every argv flag at the path, coerced once by the common type of the variants that own
  the name (`_resolve_union_field_type` / `_subclass_field_type`), and leaves the ones the named
  variant does not know for `build()` to reject; descending only into the named variant dropped
  them silently — a mistyped `--<field>` was ignored instead of refused, and a tag whose import
  failed cost the sibling flags their place in the merged dict (BUG-69). Each variant is
  descended into in its own guard, so one variant's failed import costs no other variant its
  flags.
- A flag several variants own is coerced once, by vanilla's common-or-`str` answer, never by
  the last walk: the common type when every owner resolves the path alike, the raw token —
  `str`, deferring the choice to `build()` — when they do not. The tag does not change the
  answer: vanilla resolves a path through *all* the variants whether or not one is named, so
  with a tag the adapters used to keep the named variant's coercion standing, and without one
  the last variant's (BUG-84). A per-variant walk cannot reproduce that answer, each coercing
  by its own field type, so the shared descent computes the disagreeing paths up front
  (`_collect._disagreeing_owner_flags`, vanilla's own per-variant `_resolve_field_type`
  composition, so a path several levels down answers as vanilla answers it), collects each of
  them once as the raw token, and hides them from the walks that follow — the flag's sub-flags
  keep their owners' walks, each answering the same question at its own path. The stores
  themselves are written in the order argv spells the flags, so an ancestor/descendant pair
  of conflicts answers the latest-writer question the way vanilla's sequential writes do,
  and a conflicting flag typed after its own sub-flags hides them too: vanilla's own last
  write replaced the whole subtree, and the walks must not resurrect it (BUG-85).
- A field the base class declares is answered by the **base's own** annotation, however a
  subclass overrides it: vanilla's walk consults the subclasses only for a name the base does
  not declare. The one predicate is `_types._answered_by_subclasses`, and all three walks
  consult it — vanilla's `_parse_cli._advance_field_type` of a segment, and through its path
  form `_types._base_declares_path` the collector's subclass walks
  (`_collect._collect_variant_fields` hides a base-declared first segment from them under a
  *base*, since the base's own walk already collected it) and registration's subclass recursion (`_build._collect_struct_specs` drops a subclass
  spec under a base-declared field). So a base-declared field is never a disagreeing-owner
  conflict either, and an overriding subclass registers no flag below it: a sub-flag only the
  override's struct owns is refused at parse time, as vanilla refuses it, rather than
  collected. Each subclass walk re-collecting the field by its own type let the last one's
  coercion stand (`--x.a 7` arrived as `7.0` under a `float` override of an `int` field), and
  registering the override's subtree accepted flags vanilla refuses (BUG-86).
- The descent itself is one shared walk — `_collect._collect_variant_fields` — for every
  spelling: a tag's named variant and its siblings, a union field's variants without a tag,
  the union root's, and a base class's subclasses without a tag (`_dataclass_subclasses`, the
  same set vanilla's `_subclass_field_type` searches); the two no-tag union loops were plain
  per-variant loops until BUG-84 consolidated them into the shared one. The no-tag
  inheritance branch once returned before any descent, so a subclass's flag registered in the
  flat namespace never reached the merged dict while vanilla coerced it by the owning
  subclass's field type and let `build()` raise the missing-discriminator complaint (BUG-83).
- Force-cast flags (`--f.int`, …) are registered statically only where the stealing rule is
  non-obvious: an enum variant, or `str` next to any other variant. On a plain leaf field the
  same flags register dynamically, only when typed (BUG-72) — the leaf has no stealing rule
  to be non-obvious, so static registration would be pure `--help` noise.

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

  The argparse completion pre-extend resolves the tags it reads through
  `_collect._tag_named_struct`.
- A path whose type shows no subclass accepts the tag too, and so does any other path the
  walk reaches the tag at: a struct with no subclasses, a leaf field, a namedtuple, a
  scalar root. Vanilla's tag rule answers the segment whatever the parent, and `build()`
  raises its own complaint for a class path that selects nothing. The static walk registers
  the tag only where it can see subclasses. Everywhere else the tag is registered when typed
  ([a tag is a replayed write](collection-patch-parity.md#a-tag-is-a-replayed-write);
  BUG-92, BUG-106).
- A field the base class declares is answered by the **base's own** annotation, however a
  subclass overrides it: vanilla's walk consults the subclasses only for a name the base does
  not declare. The one predicate is `_types._answered_by_subclasses`: vanilla's
  `_parse_cli._advance_field_type` asks it of a segment, and registration's subclass recursion
  asks its path form `_types._base_declares_path` (`_build._collect_struct_specs` drops a
  subclass spec under a base-declared field), so an overriding subclass registers no flag below
  it and a sub-flag only the override's struct owns is refused at parse time, as vanilla
  refuses it (BUG-86).
- What the flags write is vanilla's loop's answer
  ([argv is the only writer](model.md#argv-is-the-only-writer)): the tag kept as the raw string
  before its import resolves, so `construct()` raises the import error naming the bad path
  (BUG-45); every flag at the path, whichever variant owns it, for `build()` to reject the ones
  the named variant does not know (BUG-69, BUG-83); a flag several variants own coerced once,
  by the common type when every owner resolves it alike and the raw token when they do not
  (`_resolve_union_field_type` / `_subclass_field_type`, BUG-84); a base-declared field by the
  base's annotation (BUG-86); each occurrence where argv puts it (BUG-85, BUG-87). Each of
  those was a bug while the adapters collected the CLI channel with a walk of their own over
  the framework's parse result, descending into each variant and subclass in turn
  (`_collect_named_variant`, `_collect_variant_fields`, `_disagreeing_owner_flags`): a walk per
  variant coerces by that variant's type, writes in declaration order, and drops what no
  variant it walked owns. A tag a `--config` file sets is imported before the loop walks
  (`_tags.import_tagged_classes`), for the adapters exactly as for vanilla.
- Force-cast flags (`--f.int`, …) are registered statically only where the stealing rule is
  non-obvious: an enum variant, or `str` next to any other variant. On a plain leaf field the
  same flags register dynamically, only when typed (BUG-72) — the leaf has no stealing rule
  to be non-obvious, so static registration would be pure `--help` noise.

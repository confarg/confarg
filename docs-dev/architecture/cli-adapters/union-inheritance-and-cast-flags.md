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
- With a tag present, the collector descends into the **other** variants at the path too, not
  only the named one: the union's remaining struct variants, or the base's remaining subclasses
  (`_dataclass_subclasses`, the same set vanilla's `_subclass_field_type` searches). Vanilla
  keeps every argv flag at the path, coerced by whichever variant owns the name
  (`_resolve_union_field_type` / `_subclass_field_type`), and leaves the ones the named variant
  does not know for `build()` to reject; descending only into the named variant dropped them
  silently — a mistyped `--<field>` was ignored instead of refused, and a tag whose import
  failed cost the sibling flags their place in the merged dict (BUG-69). Each variant is
  descended into in its own guard, so one variant's failed import costs no other variant its
  flags.
- The descent itself is one shared walk — `_collect._collect_variant_fields` — for every
  spelling: a tag's named variant and its siblings, a union field's variants without a tag,
  the union root's, and a base class's subclasses without a tag (`_dataclass_subclasses`, the
  same set vanilla's `_subclass_field_type` searches). The no-tag inheritance branch once
  returned before any descent, so a subclass's flag registered in the flat namespace never
  reached the merged dict while vanilla coerced it by the owning subclass's field type and
  let `build()` raise the missing-discriminator complaint (BUG-83).
- Force-cast flags (`--f.int`, …) are registered statically only where the stealing rule is
  non-obvious: an enum variant, or `str` next to any other variant.

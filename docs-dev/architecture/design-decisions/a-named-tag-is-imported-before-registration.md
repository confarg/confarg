# A named tag is imported before registration

Whatever the configuration names by its `union_tag` — on argv, or in a `--config` file argv
points at — is imported before anything walks the target type (`_tags.import_tagged_classes`,
called from `_parse_cli` and `build_static_flags`). A subclass exists, as far as
`__subclasses__()` is concerned, only once its module has run, and five separate readers
depend on that answer: the CLI selector spec, the subclass field specs, the completer paths,
vanilla's `_subclass_field_type` path resolution, and completion's parser pre-extension. Each
of them was import-order-dependent; making the import happen first fixes all five at once.

The rejected alternative was to make registration independent of `__subclasses__()` — register
`--<field>.<union_tag>` on every struct field, since `build()` accepts the tag on any struct.
It closes the CLI half and nothing else: vanilla still cannot resolve `--handler.path` for a
subclass nobody imported, so it buys a `--help` entry per nested struct and leaves the parity
gap open one channel over. `_construct_struct_dispatch` already checks `union_tag in data`
*before* `tp.__subclasses__()`; this makes the CLI agree with it rather than inventing a second
rule.

- Cost: a `populate_*` call imports modules the command line names, so a class path is
  side-effecting at registration time and not only at construction time. confarg already
  imported `--<field>.class` targets there for callables, so the exposure is not new. A failed
  import is swallowed — it is a visibility hint, not a decision point, and `construct` raises
  the authoritative `SymbolImportError` naming the path a moment later.
- Cost: a subclass that nobody imported *and* nobody names is still absent from `--help`
  ([limitations](../limitations.md)).

This completes [no implicit subclass inference](no-implicit-subclass-inference.md#no-implicit-subclass-inference) rather than
reopening it: confarg still never *searches* for a subclass. It imports exactly the one class
the user named, which is what the tag is for.

Precedent: jsonargparse resolves a `class_path` by importing it during `parse_args`, and its
help reports `known subclasses:` from whatever is loaded — naming a class earlier on the same
command line grows the list (verified, jsonargparse 4.52.0). It accepts the same
import-dependent help this decision accepts, and answers discovery with a separate on-demand
`--<field>.help CLASS_PATH` action instead of pre-registering anything
([FEAT-15](../../todo/features/FEAT-15-inspect-flags-of-unnamed-class.md)).

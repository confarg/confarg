# Casts and reserved words

## Force casts

`.str`, `.int`, `.float`, `.bool` and `.json` suffixes pin how a value is interpreted,
bypassing the type-directed coercion (notably the stealing rule,
[types](../types/stealing-rule.md#stealing-rule)).

- `_cast.py` owns **what** the cast names are and **what value** each produces, so vanilla,
  adapters and env produce byte-identical results. `detect_force_cast` owns **whether** a
  trailing segment is a cast, because that needs the type walk.
- Scalar casts store a `_Pinned` (deferred single-type coercion). `.json` decodes eagerly and
  hard-errors on invalid JSON: an explicit request deserves a loud failure, not a fallback.
- Occurrences write sequentially, so of the plain flag and its cast spellings at one field the
  last typed wins — and the pinning being deferred, only the survivor's coercion runs, so a
  cast a later occurrence replaced never errors. The adapters read that order back off argv
  (`cli/_collect._last_leaf_cast_spelling`).
- JSON-decoded values are stored raw (not tokens), so their elements are exempt from the
  stealing rule (`"yes"` stays a string) and `null` becomes expressible inside a list.
- Root `--json` injects a whole config. It is folded in **under** the per-field flags (field
  flags refine it); with several `--json`, the later wins. At the root only `--json` is a
  cast; scalar casts have nothing to attach to. The environment has the same root form,
  `<PREFIX>JSON` ([environment parsing](../environment-parsing.md#environment-parsing)).

## Real field wins

A reserved word never shadows a real member: a field named `json` beats the `.json` cast, a
field named `locals` beats the locals namespace. One predicate decides it everywhere,
`_segment_names_real_field`: the union tag, structs (a subclass-only field included),
namedtuples and (recursively) union variants are
checked for the name; dicts accept any key so the name is always real there; lists, sets,
tuples, callables and scalars have no named members, so the word is reserved.

Keep this predicate canonical: casts, the locals name derivation, the env `__json` cast, the
env channel's unknown-field warning (BUG-90) and the adapters' `_find_json_cast`/`apply_root_json` all rely on it answering identically.

The union tag yields the same way (BUG-102): a field whose exact spelling equals `union_tag`
is that field, and the tag applies only where no member of that spelling exists — the
previously unsettled tag counterpart of this rule. A subclass-only field is such a member
too (BUG-103): the walk had always answered it so (`_subclass_field_type`), while the
predicate asked the base's own fields only, so construction read the merged key as the tag,
imported the field's value as a class path and stripped it — the field the user had set was
then reported missing. The predicate now answers with the walk, and construction, holding a
key a subclass-only field owns, selects the subclass structurally the way the union's
fallback selects a variant (`_construct_shadowed_subclass`): several matches are a loud
ambiguity, none a loud refusal. The walk asks it as "member first, tag fallback"
(`_resolve_field_type` advances before it falls back to the tag; its two mirrors,
`_addresses_callable_key` and `_is_collection_patch_path`, follow), and every site that has
only the type and the key — construction's struct, union and taggable-leaf dispatches, the
tag collectors in `_tags.py`, the adapters' tag flags — asks `_union_tag_shadowed`
(`_types.py`), the one predicate for "does a real field own the tag's spelling here?". The
tag still counts as a member for the casts and the locals (`_segment_names_real_field`
answers it so), and the CLI keeps a case-differing field distinguishable, exact matching
being what it is: `--Kind` the tag, `--kind` the field.

The trade-off is accepted the way the casts rule accepts its own: a member that shadows the
tag makes the tag's class-path dispatch unreachable at that position, silently — a variant
field shadowing a union, a base field shadowing subclass dispatch, a subclass-only field
turning subclass dispatch structural, a leaf parameter shadowing the only hatch into a
registered leaf. The alternatives were refused: refusing the collision loudly would
break plain structs that never use a union and contradict the env channel's settled
member-wins (BUG-101), and letting the tag win everywhere is the unreachable-field bug
itself. The remedy for a shadowed tag is to rename the field or pass a different
`union_tag`.

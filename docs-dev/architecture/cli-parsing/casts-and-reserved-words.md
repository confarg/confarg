# Casts and reserved words

## Force casts

`.str`, `.int`, `.float`, `.bool` and `.json` suffixes pin how a value is interpreted,
bypassing the type-directed coercion (notably the stealing rule among the variants the field
holds,
[types](../types/stealing-rule.md#stealing-rule)) — never the field's type itself.

- A cast names a type the field's annotation holds — its own type for a leaf, a variant for
  a union, anything for `Any` — and a cast naming anything else is refused, on every channel
  and front-end alike (BUG-210): an int where the config asked for a `tuple[int, int]`, a
  `str`, a list or a struct is a value the field does not accept
  ([design decisions](../design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds)).
  `_cast.holds_the_cast` owns the admission; `detect_force_cast` asks it, so vanilla's parse
  and the adapters' registration refuse the same spellings, and `construct()` asks it of a
  file's `__cast__` pin and of a stored `_Pinned` alike.
- `_cast.py` owns **what** the cast names are and **what value** each produces, so vanilla,
  adapters and env produce byte-identical results. `detect_force_cast` owns **whether** a
  trailing segment is a cast, because that needs the type walk.
- Scalar casts store a `_Pinned` (deferred single-type coercion). `.json` decodes eagerly and
  hard-errors on invalid JSON: an explicit request deserves a loud failure, not a fallback.
- Occurrences write sequentially, so of the plain flag and its cast spellings at one field the
  last typed wins — and the pinning being deferred, only the survivor's coercion runs, so a
  cast a later occurrence replaced never errors. The adapters' CLI channel is the same loop
  ([CLI adapters](../cli-adapters/model.md#argv-is-the-only-writer)), so the order holds there
  too (BUG-95 was the read-back that once stood in for it, missing a union's cast).
- JSON-decoded values are stored raw (not tokens), so their elements are exempt from the
  stealing rule (`"yes"` stays a string) and `null` becomes expressible inside a list.
- Root `--json` injects a whole config. It is folded in **under** the per-field flags (field
  flags refine it); with several `--json`, the later wins. At the root only `--json` is a
  cast; scalar casts have nothing to attach to. The environment has the same root form,
  `<PREFIX>JSON` ([environment parsing](../environment-parsing.md#environment-parsing)).
  The fold is one function, `_cast.fold_root_json`, that all three channels call (REF-44).
  A field delete beside the root cast deletes in the decoded object and in the layers below alike, as it does without the cast ([pipeline](../pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too), BUG-186).
- On a **scalar** root there are no fields to fold under: `--<prefix>` and `--<prefix>.json`
  are two spellings of one value, so the rule above for a field and its casts applies, and
  the last one typed wins, on the adapters too, whose CLI channel is the same loop. That is
  also how argparse and click treat a dest given twice. Letting the plain value always
  win was rejected: it borrows the struct root's "fields refine the object" rule where
  there is nothing to refine, and it contradicts the per-field rule.

## Real field wins

A reserved word never shadows a real member: a field named `json` beats the `.json` cast, a
field named `locals` beats the locals namespace. One predicate decides it everywhere,
`_segment_names_real_field`: the union tag, structs (a subclass-only field included),
namedtuples and (recursively) union variants are
checked for the name; dicts accept any key so the name is always real there; lists, sets,
tuples, callables and scalars have no named members, so the word is reserved. The CLI asks it
of the walk target, so a dict *root*, whose keys no flag addresses, leaves `json` to the root
cast ([cli_prefix](cli-prefix.md#a-non-struct-root-is-set-whole)).

Keep this predicate canonical: casts, the locals name derivation, the env `__json` cast, the
env channel's unknown-field warning (BUG-90) and the adapters' cast-flag registration all rely on it answering identically.

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
(`_walk_path` advances before it falls back to the tag, and every question about a path,
`_resolve_field_type`, `_addresses_callable_key` and `_is_collection_patch_path` alike, reads
that one walk), and every site that has
only the type and the key — construction's struct, union and taggable-leaf dispatches, the
tag collectors in `_tags.py`, the adapters' tag flags — asks `_union_tag_shadowed`
(`_types.py`), the one predicate for "does a real field own the tag's spelling here?". The union's structural check reads a variant's keys through one helper, `typedload._construct._field_keys`, at the variant and at a nested struct value alike; the nested check once dropped the tag-shaped key unconditionally, so a real field one level below a variant was read as the tag and the union reported an ambiguity it should have resolved (BUG-107). The merge asks the same predicate, so a key a member owns refines what lower layers set rather than replacing it ([the type decides](../design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)). The
tag still counts as a member for the casts and the locals (`_segment_names_real_field`
answers it so), and the CLI keeps a case-differing field distinguishable, exact matching
being what it is: `--Kind` the tag, `--kind` the field.

The trade-off is accepted the way the casts rule accepts its own: a member that shadows the
tag makes the tag's class-path dispatch unreachable at that position — a variant field
shadowing a union, a base field shadowing subclass dispatch, a subclass-only field
turning subclass dispatch structural, a leaf parameter shadowing the only hatch into a
registered leaf. Where the tag was a real alternative, the surprise is named instead of
stayed silent: consuming a shadowed tag-shaped key at a dispatch position emits a
`ConfargWarning`, once per position, on use
([design decisions](../design-decisions/a-shadowed-tag-warns-on-use.md#a-shadowed-tag-warns-on-use));
a position that never could dispatch stays quiet. The alternatives were refused: refusing
the collision loudly would break plain structs that never use a union and contradict the
env channel's settled member-wins (BUG-101), and letting the tag win everywhere is the
unreachable-field bug itself. The remedy for a shadowed tag is to rename the field or pass
a different `union_tag`.

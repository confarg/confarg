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
- JSON-decoded values are stored raw (not tokens), so their elements are exempt from the
  stealing rule (`"yes"` stays a string) and `null` becomes expressible inside a list.
- Root `--json` injects a whole config. It is folded in **under** the per-field flags (field
  flags refine it); with several `--json`, the later wins. At the root only `--json` is a
  cast; scalar casts have nothing to attach to. The environment has the same root form,
  `<PREFIX>JSON` ([environment parsing](../environment-parsing.md#environment-parsing)).

## Real field wins

A reserved word never shadows a real member: a field named `json` beats the `.json` cast, a
field named `locals` beats the locals namespace. One predicate decides it everywhere,
`_segment_names_real_field`: structs, namedtuples and (recursively) union variants are
checked for the name; dicts accept any key so the name is always real there; lists, sets,
tuples, callables and scalars have no named members, so the word is reserved.

Keep this predicate canonical: casts, the locals name derivation, the env `__json` cast and
the adapters' `_find_json_cast`/`apply_root_json` all rely on it answering identically.

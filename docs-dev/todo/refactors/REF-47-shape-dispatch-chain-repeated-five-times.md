# REF-47 — The shape-dispatch chain is repeated five times

**Where:** `src/confarg/typedload/_construct.py`, `src/confarg/_serialize.py` (twice),
`src/confarg/_parse_cli.py`, `src/confarg/_parse_env.py` · **Filed:** 2026-09-24
**Effort:** L · **Risk:** high · **Impact:** none

The ordered predicate chain — namedtuple, struct, union above, then `list`/`set`/`frozenset`,
then `tuple`, then `dict` — is written out verbatim in `_construct_typed`, `_serialize_by_type`,
`_serialize._variant_holds`, `_parse_cli._advance_field_type` and `_parse_env._match_env_part`.
The *predicates* are canonical (`_types.py` owns every one of them, and no module outside it
re-derives `get_origin`/`get_args`); what is duplicated is the **order they are asked in**, which
matters because the categories overlap — a namedtuple is also a tuple, a `Path` is also a leaf.

`_serialize.py` maintains that order by prose: a comment saying it "asks the shape functions in
the order `_serialize_by_type` dispatches in". An ordering invariant kept by comment across five
sites is the thing to fix.

Fix direction: one canonical `_types._type_kind(tp)` returning the category, with each of the five
sites becoming a lookup.

Size this by risk, not by lines. The net saving is only about 20 lines; the value is that the
order gains a single owner and joins
[09-invariants.md#delegate-to-the-canonical-function](../../architecture/09-invariants.md#delegate-to-the-canonical-function).
Risk is **high** because it touches both engines and two channels at once, so a mistake is silent
everywhere simultaneously. Do not file or schedule this as a footprint win.

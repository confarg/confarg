# REF-69 — Two construction-error sentences are still spelled at every call site in `typedload/`

**Where:** `src/confarg/typedload/_construct.py`, `src/confarg/typedload/_coerce.py` ·
**Filed:** 2026-09-29
**Effort:** S · **Risk:** low · **Impact:** none

[REF-51](../../architecture/10-design-decisions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)
gave the duplicated messages it named a factory on their exception class and left the rest. Two
families in `typedload/` are the next ones to have earned it, both already routed through
`_src_type` and `dotted_name` so only the sentence is left:

- **"Cannot construct `<what>` at '`<path>`': expected `<shapes>`, got `<type>` `<value>`"** — five
  sites in `_construct.py` (the namedtuple fallback, the list branch of `_construct_collection`,
  `_build_items`, `_construct_tuple`, `_construct_struct_dispatch`), differing only in the list
  of accepted shapes. One `TypeCoercionError.wrong_shape(what, accepted, data, path)` collapses
  them, and then the phrasing of "expected … got …" cannot drift the way the quoting of
  *Unknown argument* did.
- **"Class `<X>` at '`<path>`' is not a subclass of `<Y>`."** — verbatim three times, twice in
  `_coerce._coerce_type_ref` (once for a real class, once for the dotted string the user typed)
  and once in `_construct._construct_by_class_path`. The three name `X` differently and that is
  the only reason they were written out separately; the factory takes the already-formatted name.

No behavior change is intended: every message keeps its current text. Both sentences are still
formatted at the call site because `exceptions.py` may import nothing from `confarg`
([09-invariants.md#fragile-couplings](../../architecture/09-invariants.md#fragile-couplings)):
the caller has to pass `_src_type(data)` and `dotted_name(...)` in as text, which is what the
factory signatures sketched above do.

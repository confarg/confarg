# REF-69 — Two construction-error sentences are still spelled at every call site in `typedload/`

**Where:** `src/confarg/typedload/_construct.py`, `src/confarg/typedload/_coerce.py` ·
**Filed:** 2026-09-29
**Effort:** S · **Risk:** low · **Impact:** none

[REF-51](../../architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)
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

A third, filed after the other two: BUG-103 added `_construct._ambiguous_subclass_msg` as a
near-copy of `_ambiguous_union_msg`. The per-variant breakdown loop is the same, and only the
header and the remedy line differ. One builder parametrized by those two lines serves both.

A fourth, filed while closing REF-79: the none-sentinel remedy line
**"To set this field to None, pass 'none' or 'null'."** is spelled at two sites in
`_construct.py` — appended to the single-non-None-variant message (line 719) and to the union
no-match message (line 883, reached e.g. by `Union[int, bool, None]` refusing `notanint`).
Only the first is pinned to the full spelling: `tests/test_errors.py`
(`test_optional_int_null_string_hints_none_sentinel_cli`/`_env`) matches `'none' or 'null'`,
while every test reaching the second matches only `To set this field to None`
(`tests/test_corner_cases.py`, `tests/test_env.py`), so its sentinel spelling can drift
invisibly — the same drift REF-79 closed on the help side. One shared builder for the sentence
keeps the two sites single-sourced.

No behavior change is intended: every message keeps its current text. Both sentences are still
formatted at the call site because `exceptions.py` may import nothing from `confarg`
([invariants.md#fragile-couplings](../../architecture/invariants.md#fragile-couplings)):
the caller has to pass `_src_type(data)` and `dotted_name(...)` in as text, which is what the
factory signatures sketched above do.

---
filed: 2026-10-20
where:
  - src/confarg/typedload/_coerce.py
  - src/confarg/typedload/_construct.py
  - src/confarg/_serialize.py
  - src/confarg/_api.py::_named
effort: S
risk: low
impact: none
severity: trivial
---

# REF-97 — How a message names a type is spelled by hand in a dozen places

`getattr(tp, "__name__", …)` with a fallback is how a refusal names an annotation, and it is spelled by hand with drifting fallbacks: `_api._named` (`str(target)`), `_construct._variant_name` (`repr(variant)`, with `None` special-cased), `_serialize._refuse_an_unsupported_leaf` (`repr(tp)` while reading the name off `resolved`), `_serialize._serialize_dict` and `_serialize._check_native_types` (`repr`), `_coerce._registration_refusal` (`tp` itself), `register_leaf_type`'s refusal (`repr` again) — beside the older sites in `_construct` (`_construct_scalar`'s `tp_name`), `_parse_cli` (`_check_reserved_key_conflict`), `_callable` (`_check_callable_signature`) and `cli/_build` (`_argument_specs_from_signature`, `_collect_callable_factory_specs`).
`_merge._refuse_a_position_list_delete` spells a ninth way, `f"namedtuple {fixed.__name__}"` or `f"{fixed}"`.
The sibling for a position is [REF-109](REF-109-a-message-names-the-root-position-by-hand.md).
Seven of these were added by the range that closed BUG-222, BUG-253 and FEAT-51.

`exceptions.py` cannot host the helper ([it imports nothing from confarg](../../architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)), so `_types` is the home, beside `_src_type` — which answers the same question for a *value* — and the message factories take its text in, as they take `_spell_field_path`'s.

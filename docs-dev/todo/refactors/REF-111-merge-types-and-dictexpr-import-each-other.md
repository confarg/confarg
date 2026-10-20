---
filed: 2026-10-20
where:
  - src/confarg/_merge.py
  - src/confarg/_types.py
  - src/confarg/_depth.py
  - src/confarg/dictexpr/_expressions.py::_list_index
  - src/confarg/_default_layer.py::_index_keyed
effort: M
risk: low
impact: none
severity: trivial
---

# REF-111 — `_merge`, `_types` and `dictexpr` import each other, through two small leaves

The range since FEAT-43 added six function-level imports whose `noqa: PLC0415` reason is an import cycle — four in `_merge` (`_patch_needs_the_type`, `_unset_positions`, `_refuse_a_position_list_delete`, `_stands_for_a_value`), one in `_default_layer._index_keyed`, one in `_parse_cli._parse_cli` — and `_depth` imports `_types` as a module for the same reason.
The cycle has two roots, both small pure leaves living in heavy modules:

- `dictexpr._expressions._list_index`, which `_types` imports, so `_types` pulls in the expression engine and `_merge` cannot import `_types`;
- `_merge.ListOp`, which `dictexpr` and `_depth` import, so `_merge` cannot import `dictexpr` — which is all `_merge._stands_for_a_value` exists for, a rename of `dictexpr.is_whole_expression` that defers the import.

Fix direction: move `ListOp` (with `MERGE_OP_KEYS`) and `_list_index` into a leaf module that imports nothing from confarg but `_defaults`, re-exported where they are imported today; the deferred imports and `_stands_for_a_value` then go.
Unblocks [REF-110](REF-110-a-node-of-list-ops-is-told-by-hand-beside-holds-list-ops.md).

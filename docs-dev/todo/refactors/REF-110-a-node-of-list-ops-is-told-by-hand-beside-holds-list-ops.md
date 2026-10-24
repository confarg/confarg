---
filed: 2026-10-20
where:
  - src/confarg/dictexpr/_expressions.py::_holds_list_ops
  - src/confarg/_default_layer.py
  - src/confarg/_pipeline.py::_LayerReading
effort: S
risk: low
impact: none
severity: trivial
blocked_by: [REF-111]  # the helper's home is the module the cycle fix creates
---

# REF-110 — A node of pending list ops is told by hand beside `_holds_list_ops`

`any(isinstance(k, ListOp) for k in node)` — "does this node hold a pending list op?" — is written four times in `_default_layer` (`_untyped_lists`, `_union`, `_applied_over_nothing`, `_lay_unset_positions`) and once in `_pipeline._LayerReading.read`, beside `dictexpr._expressions._holds_list_ops`, which answers it with the dict check included.
All six arrived with BUG-219/BUG-220 and BUG-243.

Fix direction: one predicate next to `ListOp`, which every site asks; `dictexpr` cannot be imported from `_merge` today, which is why it lives where it does, hence the block on [REF-111](REF-111-merge-types-and-dictexpr-import-each-other.md).

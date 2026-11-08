---
filed: 2026-10-27
where:
  - src/confarg/typedload/_construct.py::_construct_collection
  - src/confarg/typedload/_construct.py::_build_items
  - src/confarg/typedload/_construct.py::_try_coll_variants
  - src/confarg/typedload/_construct.py::_try_fixed_seq_variants
effort: S  # one module; the union's sequence routing is the only care
risk: medium  # only Python data carries a tuple, so a mistake is silent in build() and a call's value alone
impact: behavior  # a tuple refused under a list field starts building
severity: minor  # passing a list instead works
---

# FEAT-60 — A tuple reads where a list reads

A list-kind node (`list[int]`, `Sequence[int]`, a `list` subclass) reads a list or an index-keyed dict only, so `build(F, {"xs": (1, 2)})` is refused with `expected list or dict with integer keys, got tuple`, where a tuple node already reads a list and a set node a tuple.
No file, variable or flag spells a tuple; a caller's `build()` data and a `call:` value do.

Settled in [the plan](../plans/a-calls-value-is-read-by-construction.md#a-tuple-reads-where-a-list-reads): a tuple reads as the sequence it spells and builds the node's list, in a union too; a set stays refused under a list, having no positions.
[BUG-293](../bugs/BUG-293-a-call-result-is-taken-unchecked-when-its-outer-class-matches.md) waits for it: once a call's value goes through construction, a call returning a tuple under `Sequence[int]`, taken today, would otherwise be refused.
Precedent (run): pydantic lax, msgspec and cattrs read `(1, 2)` under `list[int]` as `[1, 2]`.

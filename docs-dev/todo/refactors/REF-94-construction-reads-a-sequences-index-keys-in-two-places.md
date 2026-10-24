---
filed: 2026-10-15
where:
  - src/confarg/typedload/_construct.py::_build_items
  - src/confarg/typedload/_construct.py::_indexed_dict_to_positions
effort: S
risk: medium
impact: none
severity: trivial
---

# REF-94 — Construction reads a sequence's index keys in two places

`_indexed_dict_to_positions` reads the index keys of a fixed tuple's and a namedtuple's patch, and `_build_items` reads a list's itself, with its own `int(k)`, when the list is built from index keys alone.
The two answer the same question with different rules: the first refuses a key spelling a list op by name ("spells a list op"), the second only as no integer ("dict keys must be integer indices"), so a plain `"__append__"` a direct `build()` caller hands in is refused in two wordings, by the type ([deep merge](../../architecture/pipeline/deep-merge.md#no-channel-types-an-op)).
FEAT-43 gave both one check for a bare node delete at an index, `_refuse_an_index_delete`.
Fix direction: one reader of an index-keyed dict, the length optional, which `_indexed_dict_to_positions`'s range check and `_build_items`'s gap check both start from ([delegate to the canonical function](../../architecture/invariants.md#delegate-to-the-canonical-function)).

---
filed: 2026-10-20
where:
  - src/confarg/_pipeline.py::_LayerReading
effort: S
risk: medium
impact: none
severity: trivial  # would be a bug if the inferred loss reproduces
inferred: true  # from code reading; no configuration losing a namespace was built
---

# REF-104 — The locals layer reading combines a list item and its patch shallowly

`_LayerReading` reads one layer's pending list ops as the list they make, so a namespace in an item a list op holds is found where `build()` puts it ([locals.md](../../architecture/locals.md#a-namespace-in-an-item-a-list-op-holds)).
It applies the deletes and appends through `_merge._apply_list_ops`, but lays the index patches itself, in `_lay_index_patches`, as `{**item, **patch}` — where `_apply_list_ops`, and the merge everywhere, combine through `_merge._merge_existing_value`, the [canonical combiner](../../architecture/invariants.md#delegate-to-the-canonical-function).
A patch that refines a nested dict of the item replaces it whole here, so a namespace below that dict would no longer be found by the locals walk, and its declaration or override would go unchecked *(inferred)*.
It also reads a patch key with `int(k)`, which is what `_apply_list_ops` does too.

Fix direction: combine with `_merge_existing_value(item, patch, spelled, _SHAPE)`; if that cannot take the read patch (each value already walked by `self.read`), say why in the docstring.
Writing the configuration that loses a namespace settles whether this is a bug.

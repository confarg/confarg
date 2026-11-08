---
filed: 2026-11-07
where:
  - src/confarg/dictexpr/_expressions.py::_Path  # tuple[str | ListOp, ...], 35 uses in the module
  - src/confarg/dictexpr/_expressions.py::_step  # casts the integer key it reaches to str
  - src/confarg/dictexpr/_expressions.py::_collect_expressions
  - src/confarg/_default_layer.py::DataPath
effort: S
risk: low
impact: none
severity: trivial
---

# REF-122 — A position holds dict keys its alias types as text

`dictexpr._expressions._Path`, the type of a position inside resolution ([a position is a sequence of segments](../../architecture/expressions/values-and-references.md#a-position-is-a-sequence-of-segments)), is `tuple[str | ListOp, ...]`, but the scan names a dict entry by the key the data holds (`_collect_expressions` appends `k` as it is), so a YAML `{0: x}` or a caller's `{True: x}` puts an `int` or a `bool` in it, and `_step` returns the integer key it reaches by its digits under `cast("str", index)` (BUG-311).
`_default_layer.DataPath`, the same notion one module over, already reads `tuple[str | int | ListOp, ...]`, and still leaves out every other key type a caller's dict can hold.
The type checker therefore vouches for a `str` the code never guarantees, which is what lets a cast hide the next place a segment is used as text.

Fix direction: type a dict segment as the key it is (`Hashable`, or `object` beside `ListOp`), in `_Path` and in the signatures that take one, drop the cast in `_step`, and make `DataPath` say the same.
Risk is low: typing only, and `ty check` names every site the wider alias reaches.

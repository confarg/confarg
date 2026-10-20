---
filed: 2026-10-20
where:
  - src/confarg/dictexpr/_expressions.py::_pending_prefixes
  - src/confarg/dictexpr/_expressions.py::_step
effort: S
risk: medium
impact: none
severity: trivial
---

# REF-103 — `_pending_prefixes` walks the data by its own steps rather than `_step`

"Which node does this path segment reach, and how does the scan name it?" is `dictexpr._expressions._step`, "the one walk over the data", in the [canonical table](../../architecture/invariants.md#delegate-to-the-canonical-function); `_read_through`, added beside it, steps through it.
`_pending_prefixes`, which finds the nodes of pending list ops on a reference's path for the settle order, steps by hand instead: `part in node` for a dict, `_list_index` and a range check for a list, stopping where the path leaves the data.
The two agree on what a segment reaches today, but only `_step` is where a change to that reading (an anchor stand-in, a key the scan spells another way) would be made.

Fix direction: step with `_step`, treating its miss as the end of the walk; the `crossed` rule stays `_pending_prefixes`' own.
Risk is medium: a mistake reorders resolution silently on every channel, and the settle order is covered only by the tests BUG-219 and BUG-220 added *(inferred)*.

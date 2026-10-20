---
filed: 2026-10-20
where:
  - src/confarg/dictexpr/_expressions.py::_read_through
  - src/confarg/_depth.py::Copies
  - src/confarg/_depth.py::refuse_overflow
  - src/confarg/_files.py::_load_any
  - src/confarg/_files.py::_yaml_loader
effort: S
risk: low
impact: none
severity: minor  # an f-string per reference read; close to trivial, but it is the one hot loop resolution has
---

# REF-96 — The copy-budget refusal message is built on every expression read

`_read_through` builds its too-many-copies message — an f-string over `_spell_path(parts)!r` — before calling `copies.charge`, although the charge takes the refusal as a lambda and raises it only when the read crosses the bound.
Every reference read during resolution pays for a message that is almost never shown, and the read is walked three times as it is: `positions_below`, `_list_ops_within`, and the reader's own descent in `TypedReading.__call__`.

Every other `Copies.charge` site spells its refusal lazily: `_depth.refuse_overflow`, `_files._load_any` and the YAML merge-key charge all pass a lambda that builds the message only when it is raised.

It is also the one refusal of the budget not built by `ConfargError.too_many_copies`, the factory the other three call, so its text ("Reading … copies N positions, over the limit of …") reads unlike theirs ("Cannot … : it copies more than … positions"), against [one factory per message](../../architecture/invariants.md#delegate-to-the-canonical-function).
The lazy sites are not one spelling either: `refuse_overflow`, `_load_any` and the YAML merge key each write `spent = copies.spent; copies.charge(n, lambda: Error.too_many_copies(action, copies.bound, spent + n, …))` by hand.

Fix direction: `Copies.charge` takes the error class, the action and where it crossed, and builds the `too_many_copies` refusal itself, lazily; `_read_through` takes its text from the same factory and raises it as the engine raises its refusals, so the four sites shrink to one call each and none can build its message eagerly again.

[What copies](../../architecture/design-decisions/a-configuration-copies-at-most-100000-positions.md#what-copies)

---
filed: 2026-10-26
where:
  - src/confarg/_types.py::_is_union  # True for a Protocol a scalar satisfies
  - src/confarg/_types.py::_union_args  # spreads such a Protocol into its scalars and its tag half
  - src/confarg/_types.py::_class_of  # the tag half answers its Protocol
  - src/confarg/_types.py::_spell_type
  - src/confarg/typedload/_coerce.py::_KIND_ORDER  # the tag half is a STRUCT
  - src/confarg/typedload/_construct.py::_construct_union  # the refusal closes with the Protocol's line
  - src/confarg/exceptions.py::TypeCoercionError  # FEAT-57's tag demand names the scalars
  # and src/confarg/_conformance.py, which FEAT-57 creates: protocol_scalars
effort: L  # every walk changes its answer through the two union readers, and a design decision is recorded
risk: high  # a Protocol becomes a union in every channel and front-end at once
impact: behavior  # a Protocol field FEAT-57 reads as class: only starts taking plain values
severity: minor  # annotating the concrete scalar type instead works
blocked_by: [FEAT-57, BUG-299]  # FEAT-57 gives a Protocol its tag half and conformance; BUG-299 its cast flags
---

# FEAT-59 — A Protocol that scalars satisfy reads as the union of those scalars

Under FEAT-57 a Protocol field takes `{class: ...}` only, so a Protocol a plain value satisfies cannot be given one: `ratio: SupportsFloat` refuses `--ratio 3.5` and a file's `ratio: 3.5`, and asks for a class tag ([the Protocol plan](../plans/protocol-typed-fields.md#a-protocol-takes-no-plain-value-for-now)); a field defaulting to `1.0` dumps a file that does not load back.
jsonargparse 4.53 refuses them too: `Expected a dot import path string: 3` under `SupportsInt`, `SupportsFloat` and `SupportsIndex`.

The design is settled in [its plan](../plans/a-protocol-reads-the-scalars-that-satisfy-it.md).
In short: a Protocol that one of the five scalar types satisfies (`bool`, `int`, `float`, `str`, `None`, by FEAT-57's conformance rule) reads as the union of those scalars and of its implementers, which `class:` still names, ranked by the stealing rule; registered leaves, `Enum`, `Literal` and collections never join; a refusal names the Protocol and closes with its line naming the scalars; `--help` shows the union's flags; and the reading lives in `_union_args`, the Protocol's tag half being a private `Implementers(P)` marker.
`ratio: SupportsFloat` reads as `int | float | bool`, `name: HasUpper` as `str`, and `label: Printable` as `bool | int | float | str | None`.

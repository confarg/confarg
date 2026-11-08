---
filed: 2026-10-26
where:
  - src/confarg/_types.py::_union_args
  - src/confarg/typedload/_construct.py::_construct_union_leaf
  - src/confarg/_serialize.py::_variant_holds
effort: M
needs_design: true  # the ranking among the leaves, the help metavar, and whether registered leaves join
risk: high  # it reads a Protocol as a union, which every channel ranks
impact: behavior
severity: minor  # annotating the concrete leaf type instead works
blocked_by: [FEAT-57]
---

# FEAT-59 — A Protocol that leaves satisfy reads as the union of those leaves

Under FEAT-57 a Protocol field takes `{class: ...}` only, so a standard-library Protocol that builtins satisfy cannot be given a plain value: `ratio: SupportsFloat` refuses `--ratio 3.5` and a file's `ratio: 3.5`, and asks for a class tag ([the Protocol plan](../plans/protocol-typed-fields.md#a-protocol-takes-no-plain-value-for-now)).
jsonargparse 4.53 refuses them too: `Expected a dot import path string: 3` under `SupportsInt`, `SupportsFloat` and `SupportsIndex`.

The idea: a Protocol also reads as the union of the built-in and registered leaf types that conform to it by FEAT-57's rule, ranked as any union ranks its scalars ([a union ranks every value](../../architecture/design-decisions/a-union-ranks-every-value.md)), its implementers still named by `class:`.
`__float__` is found on `bool`, `int`, `float`, `Decimal` and `Fraction`, `__index__` on `bool` and `int`, `__len__` on `str`; collections stay out, so `Sized` does not read a list.
The design pass settles the ranking, whether a user Protocol that `str` happens to satisfy should take any text, the help metavar, and the dump.

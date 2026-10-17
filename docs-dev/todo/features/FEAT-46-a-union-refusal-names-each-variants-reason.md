---
filed: 2026-10-17
where:
  - src/confarg/typedload/_construct.py::_construct_union_leaf  # the union's one refusal
  - src/confarg/typedload/_construct.py::_first_scalar_variant_taking  # where each variant's reason is dropped
  - src/confarg/exceptions.py::TypeCoercionError
effort: M
risk: low  # messages only; the choice of variant is untouched
impact: behavior
severity: minor  # the generic refusal still names the field and the union; the reason is one lone-field load away
needs_design: true  # the effort sizes the design pass: the format and which reasons to show
---
# FEAT-46 — A union's refusal names each variant's reason

When every variant of a union refuses a value, the error names the field and the union, never why each variant refused: `Callable | Opts` refusing `"pkg.dubble"` says `Cannot coerce str 'pkg.dubble' to Callable | Opts at 'f'`, where the user needs `cannot import 'pkg.dubble': module 'pkg' has no attribute 'dubble'`. The same holds for an Enum's valid members, a Literal's choices, a class outside a `type[X]` bound. Each variant's reason is computed and dropped by the scalar walk, which catches it to try the next variant.

The design pass has to settle the format (one line per variant, as pydantic lists one error per union member, or the most specific reason alone), which reasons are worth showing (a `str` variant never refuses a string, a struct variant's "a str is no struct" says nothing), and how it combines with the none-word remedy `cannot_coerce` already appends ([construction](../../architecture/types/construction.md#an-optional-field-fails-as-its-variant)).

Raised while settling how a reference variant reads a file's string ([a union ranks every value](../../architecture/design-decisions/a-union-ranks-every-value.md#a-union-ranks-every-value)): a typo'd path in `Callable | str` silently becomes text, and in `Callable | Opts` it fails with no hint of the import.

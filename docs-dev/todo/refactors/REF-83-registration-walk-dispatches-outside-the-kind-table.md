---
filed: 2026-10-04
where:
  - src/confarg/cli/_build.py::_specs_for_field
  - docs-dev/architecture/types/introspection.md
effort: M
risk: medium
impact: none
severity: trivial
---

# REF-83 — The registration walk dispatches on shape outside `_type_kind`

REF-47 gave every shape dispatch one ordered table, `typedload._coerce._type_kind`, and converted construction, serialization, `_variant_holds` and the CLI walk.
Flag registration is a fifth walk that branches on every shape and still asks the predicates in an order of its own: union, callable, namedtuple, registered leaf, struct, dict, then the leaf/sequence fallback.
Its order differs from `_KIND_ORDER` (callable before namedtuple, a registered leaf before a struct).
That is harmless only while the predicates stay disjoint, which is exactly what [shape dispatch](../../architecture/types/introspection.md#shape-dispatch) says nothing outside the table may rely on.

The gap has already bitten once: registration unwrapped `Final` at its own site, `_type_kind` did not, and a `Final[Struct]` field registered sub-flags that the walk then refused (fixed by making `_resolve_type` unwrap `Final`).
Fix direction: `match _type_kind(core)` in `_specs_for_field`, with `TAGGABLE_LEAF` registering as a leaf, as it does today.
Then correct the note, which counts four walks.

The union branch grew a fourth question with BUG-250: beside the concrete, sequence and leaf triage it asks `_holds_a_callable` to list a Callable variant's openers (`_opener_specs`).
A `match _type_kind(...)` dispatch should keep that one question rather than another branch of its own.

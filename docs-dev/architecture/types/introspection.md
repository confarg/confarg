# Type introspection

All type knowledge is derived at runtime from ordinary annotations (`_types.py`), because
confarg requires no base class, decorator or field marker
([design decisions](../design-decisions/no-custom-types-required.md#no-custom-types-required)).

- `TypeAliasType` and `Annotated` are unwrapped everywhere (`_resolve_type`).
- Abstract collection types map to concrete ones: `Sequence`/`Iterable`/`Collection` → list,
  `AbstractSet`/`MutableSet` → set, `Mapping`/`MutableMapping` → dict.
- A **struct** is a dataclass or a *plain class* whose `__init__` takes parameters. Builtins,
  `Enum`, `PurePath` and tuple subclasses are never plain classes. `*args` becomes
  `list[T]`, `**kwargs` becomes `dict[str, T]`, both with empty defaults (never required).
- Since Python 3.11 `typing.Any` is a subclassable class and would pass the plain-class
  test; `_is_plain_class` guards it explicitly, and `_type_kind` names it `ANY` before any
  shape test runs.
- `_unwrap_optional` returns Python `None` (not `NoneType`) to mean "multi-variant union";
  callers must handle that sentinel.

## Shape dispatch

Every walk over a type tree branches on the same question — what shape is this node? — and
four of them branch on all of it: construction (`_construct_typed`), serialization
(`_serialize_by_type`), the union-variant test (`_variant_holds`) and the CLI type walk
(`_advance_field_type`, with `_is_collection_patch_path` asking the same walk a narrower
question). `typedload._coerce._type_kind` is the one answer: it asks the shape predicates in
one ordered table, `_KIND_ORDER`, and returns a `_TypeKind`; each walk is a `match` on it
(REF-47).

- **The predicates stay canonical; the table owns their order.** `_types.py` still answers
  each shape question, and `_is_struct_variant` / `_is_taggable_leaf` still answer the struct
  one. What used to be repeated was the order they were asked in, kept in step across four
  sites by a comment. Most of the predicates are disjoint, so the order matters only where
  they are not — `Any` would pass the plain-class test, and a registered leaf with `__init__`
  parameters is a struct to `_is_struct` — but nothing outside the table may rely on that
  remaining so.
- **The function lives beside the leaf registry, not in `_types.py`.** Splitting a struct
  into `STRUCT` and `TAGGABLE_LEAF` needs the registry `register_leaf_type` writes, which
  lives in `typedload/_coerce.py`, and `_coerce` already imports `_types`, so `_types` cannot
  ask it back. The CLI walk imports it from there as it already imports `_try_coerce`.
- **`TAGGABLE_LEAF` is its own kind** because the walks disagree about it on purpose:
  construction and serialization treat it as a leaf, while the CLI walk enters its members,
  because an explicit class tag may still build it from its fields
  ([design decisions](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)).
  A single `STRUCT` kind would have forced one of them to re-ask the registry at its own site.
- **`CALLABLE` is a kind too**, so `construct()` and `_serialize()` no longer test for a
  callable before handing over to the dispatch: every shape is decided in one place.
- **Each `match` lists every kind.** A walk that adds no branch for a new kind fails `ty`
  wherever the function's return type is not `Any` (an implicit `None` return), so a new
  shape is added in `_KIND_ORDER` and then in each walk, never in a walk alone.
  `_construct_typed` and `_serialize_by_type` return `Any`, so for them the list is kept by
  review and by `TestTypeKind`.

Precedents point the same way. msgspec classifies a type once — `msgspec.inspect.type_info`
and the `TypeNode` its encoder and decoder share — rather than letting each direction
re-derive it. typedload, the other way round, keeps a separate ordered `handlers` list in its
`Loader` and its `Dumper`, which is the duplication this table removes; cattrs registers
predicate hooks per direction, in an order each converter holds on its own.

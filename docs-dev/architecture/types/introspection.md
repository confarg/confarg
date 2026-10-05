# Type introspection

All type knowledge is derived at runtime from ordinary annotations (`_types.py`), because
confarg requires no base class, decorator or field marker
([design decisions](../design-decisions/no-custom-types-required.md#no-custom-types-required)).

- `TypeAliasType`, `Annotated` and `Final` are unwrapped everywhere (`_resolve_type`; see
  [wrappers are transparent](#wrappers-are-transparent)).
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

## Wrappers are transparent

`_resolve_type` unwraps `TypeAliasType`, `Annotated` and `Final` in a loop, so they nest in
any order (`Annotated[Final[X], …]`, an alias of `Final[X]`), and a bare `Final` reads as
`Any`. What each wrapper adds — an alias name, metadata, "not reassigned" — is nothing a
channel, the merge, construction or serialization acts on, so every walk asks the type
underneath.

`Final` used to be unwrapped only at the sites that remembered to: flag registration, the
argparse completion and `_coerce_leaf`. `_type_kind` did not, so a `Final[Struct]` field
registered `--inner.x` that the CLI walk then refused on every front-end, `build()` refused
its dict as an unsupported leaf, `dump()` passed the object through, and a `Final[int]` token
stayed text in the merged dict where an `int` one is coerced. A wrapper is unwrapped in the
one function every walk already calls, never at a site.

Precedents: the standard library's `dataclasses` makes a `Final`-annotated class attribute an
ordinary instance field, and msgspec and cattrs both decode and encode `Final[T]` as `T`.
pydantic instead reads a `Final` attribute with a default as a class variable, which suits a
model with validation-time defaults but not a library whose targets are plain dataclasses.

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

## Introspection is cached per class

Every channel and front-end asks the same few questions of a struct, and asks them again for
each field, each union variant and each subclass: one union disambiguation used to call
`_struct_fields` at least twice per variant before construction called it again. Each call
re-ran `get_type_hints`, and a plain class's `__init__` signature was walked by five functions,
each collecting a different attribute of the same parameters (REF-48). Two changes answer that:

- **One signature walk.** `_init_params(tp)` reads `inspect.signature(tp.__init__)` once into an
  `_InitParams` record: the parameter names, the declared defaults, the `*args` / `**kwargs`
  names (`_VarParams`) and the names a positional argument fills. `_is_plain_class`,
  `_init_fields`, `_init_defaults`, `_var_params`, `_struct_required` and the `*args` call in
  construction are views of it. The record holds nothing the annotations decide, so it stays
  valid whatever the annotations resolve to.
- **The answers are cached per class.** `_init_params`, `_dc_fields`, `_init_fields` and
  `_namedtuple_fields` are `functools.cache`d, as `cli._spec._get_field_docstrings` already
  was. A cached mapping is shared, so it is returned as a read-only `MappingProxyType`: a
  caller that mutates it fails at once rather than corrupting every later answer.
  `inspect.Signature.parameters` hands out the same read-only view, for the same reason. The
  cache is unbounded: the key is a class, and a program has as many classes as it defines.

What is never cached, and why:

- **Defaults are built per call.** `_dc_defaults` calls each `default_factory`, and
  `_init_defaults` gives `*args` and `**kwargs` a fresh `[]` and `{}`: a cached default would be
  one mutable object shared by every constructed instance. The declared defaults of a plain
  class are cached, because Python itself evaluates them once, when `__init__` is defined. A
  question that only needs to know *whether* a field has a default asks `_struct_required`,
  which builds none.
- **Nothing that reads the leaf registry.** `register_leaf_type` writes `_LEAF_COERCIONS` at
  runtime ([leaf coercion](leaf-coercion.md#leaf-coercion)), so `_is_registered_leaf`,
  `_is_struct_variant`, `_is_taggable_leaf`, `_is_eagerly_coercible` and `_type_kind` would
  keep answering for the registry as it was. Nothing in `_types.py` reads the registry, which
  is what lets its answers be cached.
- **An annotation that does not resolve.** A plain class's or a namedtuple's annotation that
  `get_type_hints` cannot resolve reads as `Any`, but that answer is not cached: a forward
  reference to a name the module defines later resolves on a later call. A dataclass's
  unresolvable annotation raises, and an exception is never cached. pydantic does the same with
  a model whose forward references are not yet defined: it stays incomplete, and is rebuilt on
  use rather than frozen with the missing type.

**`*args` is reached by position, through the record.** A class taking `*args` cannot have
its positional parameters passed by keyword, so construction passes them by position, in
order, up to the first one it has no value for. `inspect.Signature.bind_partial` would do the
same with its `BoundArguments.args`, but it binds every value it is given by keyword first and
so refuses a positional-only parameter, which the record serves as well as any other. A gap
before a non-empty `*args` raises: no call can reach `*args` past an unfilled positional
parameter, and filling the gap with the first element would build the wrong object silently.
Construction fills every declared field before the call, so the gap is unreachable today.

Precedents: the standard library's `dataclasses` computes a class's fields once and stores them
on the class (`__dataclass_fields__`), msgspec caches the type information its encoder and
decoder share on the class it describes, and `typing` caches its parameterised aliases with
`functools.lru_cache`. All three cache a structure that is fixed once the class exists, never
one that a registry can change afterwards.

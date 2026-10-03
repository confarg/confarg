# Serialization

`_serialize` is the inverse of construction for `dump()`; `_serialize_untyped` is its
counterpart for the raw dict `dump_file()` accepts, walking containers and routing every leaf
through the same `_serialize_leaf` — plus the one thing only a raw dict holds, a force-cast
`_Pinned` ([cast pinning in files](stealing-rule.md#cast-pinning-in-files)).

- `tag_policy="auto"` emits the union tag only when `_needs_tag` shows that structural
  disambiguation of the serialized data would not select exactly one variant on the way
  back in; `"always"` tags every struct union member. A subclass of the declared type is
  always tagged.
- Which union variant an instance belongs to is `_variant_holds`, asked once per variant in
  declaration order. It dispatches on the same `_type_kind` as `_serialize_by_type`
  ([shape dispatch](introspection.md#shape-dispatch)), so the variant it picks is the one that
  then serializes the value, and each
  shape answers with the concrete class construction builds for it — `list` for `Sequence[X]`,
  `dict` for `Mapping[K, V]`. A bare `isinstance` cannot ask the question at all: a
  parameterized generic and a `Literal` both refuse to be its second argument, so every union
  holding one — `list[str] | str`, `Literal["fast", "slow"] | str` — used to raise a `TypeError`
  out of `dump()` while loading fine (BUG-31, closed). A `Literal` answers by membership on the
  member's own type, so `True` is not a value of `Literal[1]`; its members are plain values, and
  `_serialize_leaf` already writes them as such, reading the value rather than the declared type.
- A **leaf** union member is written as `{__cast__, __value__}` when the bare scalar would be
  read back as another variant, under either policy
  ([casting a stolen leaf](stealing-rule.md#casting-a-stolen-leaf)).
- Enums dump as values, registered leaf types through their registered serializer (`Path`
  being the first of them, hence a string), types as dotted paths, sets sorted by
  `(type name, str)` so output is deterministic. These rules read the *value*, not the
  declared type, which is why the untyped path can share them; only widening an `int` to a
  `float` needs a type, so it never happens on a raw dict
  ([pipeline](../pipeline/api-seams.md#public-api-seams)). The `_StrToken` unwrap comes before
  the registry loop, so a token cannot be captured by a serializer registered for `str`.
- Plain classes must store every `__init__` parameter as a same-named attribute to be
  serializable.
- Callables dump via their stored spec ([callables](../callables.md#round-trip)).

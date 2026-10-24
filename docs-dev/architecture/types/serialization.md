# Serialization

`_serialize` is the inverse of construction for `dump()`; `_serialize_untyped` is its counterpart for the raw dict `dump_file()` accepts, walking containers and routing every leaf through the same `_serialize_leaf` — plus what only a raw dict holds: a force-cast `_Pinned` ([cast pinning in files](stealing-rule.md#cast-pinning-in-files)), a pending list op, written by its reserved key, and a delete, written as a file's node delete, `{__unset__: true}` for a key delete and `__unset__: true` beside the keys of a node whose base is deleted ([a file spells an op in its value](../design-decisions/a-file-spells-an-op-in-its-value.md#the-node-delete)).
Until BUG-202 a delete reached the writer, which raised its own error.

- `tag_policy="auto"` emits the union tag only when `_needs_tag` shows that structural disambiguation of the serialized data would not select exactly one variant on the way back in; `"always"` tags every struct union member.
  A subclass of the declared type is always tagged.
- Which union variant an instance belongs to is `_variant_holds`, asked once per variant in declaration order, `Any` last: it holds every instance, so it is asked after every other variant, as construction offers it a value only after every other variant refused it ([construction](construction.md#an-any-variant-is-tried-last)).
  It dispatches on the same `_type_kind` as `_serialize_by_type` ([shape dispatch](introspection.md#shape-dispatch)), so the variant it picks is the one that then serializes the value, and each shape answers with the concrete class construction builds for it — `list` for `Sequence[X]`, `dict` for `Mapping[K, V]`.
  A bare `isinstance` cannot ask the question at all: a parameterized generic and a `Literal` both refuse to be its second argument, so every union holding one — `list[str] | str`, `Literal["fast", "slow"] | str` — used to raise a `TypeError` out of `dump()` while loading fine (BUG-31, closed).
  A `Literal` answers by membership on the member's own type, so `True` is not a value of `Literal[1]`; its members are plain values, and `_serialize_leaf` already writes them as such, reading the value rather than the declared type.
- A **leaf** union member is written as `{__cast__, __value__}` when the bare scalar would be read back as another variant, under either policy ([casting a stolen leaf](stealing-rule.md#casting-a-stolen-leaf)).
- Enums dump as values, registered leaf types through their registered serializer (`Path` being the first of them, written as `as_posix()`, so a dump made on Windows reads back on any OS), types as dotted paths when the path imports back ([dotted imports](dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back)), sets sorted by `(type name, str)` so output is deterministic.
  These rules read the *value*, not the declared type, which is why the untyped path can share them; only widening an `int` to a `float` needs a type, so it never happens on a raw dict ([pipeline](../pipeline/api-seams.md#public-api-seams)).
  The `_StrToken` unwrap comes before the registry loop, so a token cannot be captured by a serializer registered for `str`.
- A dataclass is written as the fields it stores, an `init=False` one included and an `InitVar` never; a plain class as its constructor's parameters, each read from the same-named attribute, slot or property the instance holds, never from a plain class attribute ([the object dump is forensic](../design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).
- `_serialize` writes the state of the built object: resolved values, and never the `call:` that produced one ([design decision](../design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).
  Callables dump as what they are ([callables](../callables.md#round-trip)), and leave through `_serialize_untyped`, since a partial's keywords carry no declared type.
  A callable instance and a bound method's owner are serialized as structs, their fields typed ([callables](../callables.md#an-object-dumps-the-state-it-holds)).

## An unsupported leaf is refused both ways

A value typed by a leaf construction does not build — no struct, no type reference, and none of the leaves `_coerce._is_coercible_leaf` names, as `datetime.date` is until registered — is refused by `dump()` with a `ConfargError` naming the path and `register_leaf_type`, the type construction refuses as `Unsupported leaf type` (`_serialize._refuse_an_unsupported_leaf`).
One predicate answers both directions, so a value `dump()` writes is one construction can read back.
`dump()` used to pass such a value through, untouched and unwarned, and the format writer then failed with its own error (`Object of type date is not JSON serializable`) or wrote a value the reload refused.
`date` reached that path only once a class whose signature does not read stopped being a struct ([which signature is read](../design-decisions/a-structs-members-are-its-constructors-parameters.md#which-signature-is-read)); before, it was a struct with `object.__init__`'s `args` and `kwargs`, which `dump()` refused as not held.

An `Any` node still writes what it holds untyped, with a warning, since an `Any` node holds every type ([below](#an-any-node-dumps-the-spec-that-rebuilds-it)).

## An `Any` node dumps the spec that rebuilds it

An `Any` node reads every opener ([callables](../callables.md#an-any-node-reads-every-opener)), so `_serialize._serialize_any` writes what one holds by its runtime type, as the spec that rebuilds it: a dict and a list walked, each item an `Any` node in turn; a struct as `{class: <its path>, <fields>}`, its fields serialized as their types say; a callable as a Callable field writes it ([callables](../callables.md#round-trip)), with a bare path opened into `{bind: <path>}`, since an `Any` node reads a bare string as text; a leaf through `_serialize_leaf`.
`_held_object_form` is the one place that picks the form of a value that is no container.

A form is kept only if an `Any` node reads it back as the value it came from, which `_reads_back` decides by running the reader.
An object that does not compare equal to the one rebuilt — a plain class with no `__eq__`, a bound method, a partial — is the same value when the rebuilt one dumps back as the same form: it holds the same state ([an object dumps the state it holds](../callables.md#an-object-dumps-the-state-it-holds)).
Any other value is written untyped (`_serialize_untyped`), with a `ConfargWarning` naming its path and the reason: a `Path` that reads back as text, an `Enum` that reads back as its value, a `datetime`, an object no spec spells, such as a closure or a class that keeps an argument under another name.
A dict holding an opener key reads back as the spec it spells, and a tuple or a set as a list, so they warn too.
What a struct's fields warn is said only when the struct's spec is kept, so a `UUID`, which the plain-class test takes for a struct and no spec rebuilds, warns once, not once per attribute.

In a union, the `Any` variant's form is what a bare `Any` reads back; the union must read it back the same way, or it is written with its own type's cast, as a stolen leaf is ([stealing rule](stealing-rule.md#casting-a-stolen-leaf)).
An object only `Any` holds beside a struct variant is written with its `class:` tag, which names no variant and so is the `Any` variant's spec.

Before FEAT-42 an `Any` node wrote what it held untouched, and only Python code could put an object in one: `dump_file()` then failed with the writer's own error, even after a plain `load()` of a field whose default is an object.
Writing every object untyped with a warning was rejected: the object still reaches the writer ([design decision](../design-decisions/an-any-node-reads-every-opener.md)).

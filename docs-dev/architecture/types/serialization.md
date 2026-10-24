# Serialization

`_serialize` is the inverse of construction for `dump()`; `_serialize_untyped` is its counterpart for the raw dict `dump_file()` accepts, walking containers and routing every leaf through the same `_serialize_leaf` — plus what only a raw dict holds: a force-cast `_Pinned` ([cast pinning in files](stealing-rule.md#cast-pinning-in-files)), a pending list op, written by its reserved key, and a delete, written as a file's node delete, `{__unset__: true}` for a key delete and `__unset__: true` beside the keys of a node whose base is deleted ([a file spells an op in its value](../design-decisions/a-file-spells-an-op-in-its-value.md#the-node-delete)).
Until BUG-202 a delete reached the writer, which raised its own error.

- `tag_policy="auto"` emits the union tag only when `_needs_tag` shows that structural disambiguation of the serialized data would not select exactly one variant on the way back in; `"always"` tags every struct union member.
  A subclass of the declared type is always tagged.
- Which union variant an instance belongs to is `_variant_holds`, asked once per variant in declaration order, `Any` last: it holds every instance, so it is asked after every other variant, as construction offers it a value only after every other variant refused it ([construction](construction.md#an-any-variant-is-tried-last)).
  It dispatches on the same `_type_kind` as `_serialize_by_type` ([shape dispatch](introspection.md#shape-dispatch)), so the variant it picks is the one that then serializes the value, and each shape answers with the concrete class construction builds for it — `list` for `Sequence[X]`, `dict` for `Mapping[K, V]` — before a second pass widens it to what a type checker accepts ([below](#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it)).
  A bare `isinstance` cannot ask the question at all: a parameterized generic and a `Literal` both refuse to be its second argument, so every union holding one — `list[str] | str`, `Literal["fast", "slow"] | str` — used to raise a `TypeError` out of `dump()` while loading fine (BUG-31, closed).
  A `Literal` answers by membership on the member's own type, so `True` is not a value of `Literal[1]`; its members are plain values, and `_serialize_leaf` already writes them as such, reading the value rather than the declared type.
- A **leaf** union member is written as `{__cast__, __value__}` when the bare scalar would be read back as another variant, under either policy ([casting a stolen leaf](stealing-rule.md#casting-a-stolen-leaf)).
- Enums dump as values, registered leaf types through their registered serializer (`Path` being the first of them, written as `as_posix()`, so a dump made on Windows reads back on any OS), types as dotted paths when the path imports back ([dotted imports](dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back)), sets sorted by `(type name, str)` so output is deterministic.
  These rules read the *value*, not the declared type, which is why the untyped path can share them; only widening an `int` to a `float` needs a type, so it never happens on a raw dict ([pipeline](../pipeline/api-seams.md#public-api-seams)).
  An instance of a builtin's subclass is written as the builtin, whatever the field's type, since PyYAML's writer refuses a subclass, and it reads back as the subclass where the field is one ([design decisions](../design-decisions/a-builtins-subclass-is-that-builtin.md#a-subclass-is-built-by-its-constructor)).
  The `_StrToken` unwrap comes before the registry lookup, so a token cannot be captured by a serializer registered for `str`.
  A registered leaf is written by the serializer of its most specific registered type (`_coerce._registered_leaf_of`), so a `datetime` by `datetime.isoformat`, not `date`'s ([design decisions](../design-decisions/the-date-and-time-types-are-built-in-leaves.md#an-instance-is-its-most-specific-registered-type)).
- A registered leaf whose type `native_types` names is written as the object it is, for a writer that holds it: `dump_file()` passes its format's set, a `date` and a `datetime` for YAML and TOML, none for JSON.
  `_DumpOptions` carries the set, the union tag and the tag policy down every serializer, and `_serialize_untyped` takes the set too ([design decisions](../design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-writer-may-hold-a-date-natively)).
- A dataclass is written as the fields it stores, an `init=False` one included and an `InitVar` never; a plain class as its constructor's parameters, each read from the same-named attribute, slot or property the instance holds, never from a plain class attribute ([the object dump is forensic](../design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).
- `_serialize` writes the state of the built object: resolved values, and never the `call:` that produced one ([design decision](../design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).
  Callables dump as what they are ([callables](../callables.md#round-trip)), and leave through `_serialize_untyped`, since a partial's keywords carry no declared type.
  A callable instance and a bound method's owner are serialized as structs, their fields typed ([callables](../callables.md#an-object-dumps-the-state-it-holds)).

## An unsupported leaf is refused both ways

A value typed by a leaf construction does not build — no struct, no type reference, and none of the leaves `_coerce._is_coercible_leaf` names, as `complex` is until registered — is refused by `dump()` with a `ConfargError` naming the path and `register_leaf_type`, the type construction refuses as `Unsupported leaf type` (`_serialize._refuse_an_unsupported_leaf`).
One predicate answers both directions, so a value `dump()` writes is one construction can read back.
A dict's key type is asked the same, by `_coerce._is_coercible_leaf` alone since construction coerces a key as a leaf: a `dict[tuple[int, int], V]` or a `dict[int | None, V]` holding a key is refused, as construction refuses its key (`Unsupported leaf type`), where `dump()` used to write a dict that did not load back.
A `Literal` holding a member PEP 586 forbids is refused by both with the same error, and a value that is a `bytes` member of a `Literal` is refused as a `bytes` field's is ([design decisions](../design-decisions/a-literal-member-is-what-pep-586-allows.md#a-literal-member-is-what-pep-586-allows)).
`dump()` used to pass such a value through, untouched and unwarned, and the format writer then failed with its own error (`Object of type date is not JSON serializable`) or wrote a value the reload refused.
`date` reached that path only once a class whose signature does not read stopped being a struct ([which signature is read](../design-decisions/a-structs-members-are-its-constructors-parameters.md#which-signature-is-read)); before, it was a struct with `object.__init__`'s `args` and `kwargs`, which `dump()` refused as not held.
It is a built-in leaf since ([the date and time types](../design-decisions/the-date-and-time-types-are-built-in-leaves.md#the-date-and-time-types-are-built-in-leaves)).

An `Any` node still writes what it holds untyped, with a warning, since an `Any` node holds every type ([below](#an-any-node-dumps-the-spec-that-rebuilds-it)).

## An `Any` node dumps the spec that rebuilds it

An `Any` node reads every opener ([callables](../callables.md#an-any-node-reads-every-opener)), so `_serialize._serialize_any` writes what one holds by its runtime type, as the spec that rebuilds it: a dict and a list walked, each item an `Any` node in turn; a struct as `{class: <its path>, <fields>}`, its fields serialized as their types say; a callable as a Callable field writes it ([callables](../callables.md#round-trip)), with a bare path opened into `{bind: <path>}`, since an `Any` node reads a bare string as text; a leaf through `_serialize_leaf`.
`_held_object_form` is the one place that picks the form of a value that is no container.

A form is kept only if an `Any` node reads it back as the value it came from, which `_reads_back` decides by running the reader.
An object that does not compare equal to the one rebuilt — a plain class with no `__eq__`, a bound method, a partial — is the same value when the rebuilt one dumps back as the same form: it holds the same state ([an object dumps the state it holds](../callables.md#an-object-dumps-the-state-it-holds)).
Any other value is written untyped (`_serialize_untyped`), with a `ConfargWarning` naming its path and the reason: a `Path` that reads back as text, an `Enum` that reads back as its value, a `datetime`, an object no spec spells, such as a closure or a class that keeps an argument under another name.
A value of a leaf construction does not build, a `complex`, a `bytes`, an `object()` or a lock, is refused by `_held_object_form` with the refusal a field of its type gets (`_refuse_an_unsupported_leaf`, [above](#an-unsupported-leaf-is-refused-both-ways)), so it warns too.
Until BUG-268 it was handed back untouched and kept, unwarned: an `Any` node passes an object through, so the reader rebuilt it from itself.
A dict holding an opener key reads back as the spec it spells, and a tuple or a set as a list, so they warn too.
What a struct's fields warn is said only when the struct's spec is kept, so a plain class no spec rebuilds, such as one holding every alternative its constructor takes, warns once, not once per attribute.

In a union, the `Any` variant's form is what a bare `Any` reads back; the union must read it back the same way, or it is written with its own type's cast, as a stolen leaf is ([stealing rule](stealing-rule.md#casting-a-stolen-leaf)).
An object only `Any` holds beside a struct variant is written with its `class:` tag, which names no variant and so is the `Any` variant's spec.

Before FEAT-42 an `Any` node wrote what it held untouched, and only Python code could put an object in one: `dump_file()` then failed with the writer's own error, even after a plain `load()` of a field whose default is an object.
Writing every object untyped with a warning was rejected: the object still reaches the writer ([design decision](../design-decisions/an-any-node-reads-every-opener.md)).
It still reaches `dump_file()`, which refuses it with a `ConfargError` naming its path before anything is written ([a written file holds what its reader reads back](../design-decisions/a-written-file-holds-what-its-reader-reads-back.md#a-written-file-holds-what-its-reader-reads-back)); until BUG-251 the writer raised its own error, into a file it had already truncated.

## A value its type does not hold dumps as an `Any` node holds it

A value its declared type does not hold — a `Bar` in a field typed `Empty`, a `3` in a struct field, `'abc'` in an `int` field, a `None` in a field that lists no `None`, a three-item tuple in a `tuple[int, int]` — is written as an `Any` node writes it, by its runtime type ([above](#an-any-node-dumps-the-spec-that-rebuilds-it)), with a `ConfargWarning` naming the path, the value's class and the declared type (`_serialize._serialize_foreign`, BUG-267).
The object dump is forensic, so it records what the object holds rather than refusing it ([the object dump is forensic](../design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)), and the warning says that the dump will not read back.
A value no spec spells is written untyped.

Whether the type holds the value is `_serialize._holds`, asked before anything else of the value, and answered by the predicate that already picks a union's variant (`_variant_holds`), widened to what a type checker accepts for the annotation: an abstract collection holds any instance of its abstract class (a tuple in a `Sequence[int]`, a `frozenset` in an `AbstractSet[int]`, a `MappingProxyType` in a `Mapping[str, int]`), a str or bytes apart for a sequence, and a `float` holds an int, PEP 484's numeric tower.
A union holds what one of its variants holds, an exact holder preferred over a widened one, so `float | int` still writes `1` as the int it is.
A type construction does not build at all is still refused first, whatever the value ([above](#an-unsupported-leaf-is-refused-both-ways)).

A plain class's `*args` member is typed as the tuple Python hands the constructor, `tuple[T, ...]`, when the dump reads what the instance holds, where it is a `list[T]` as a member every channel sets (`_types._struct_state_fields`): `self.items = items` keeps that tuple.

Before, each shape answered differently, and none warned: a struct field read its declared fields off whatever it held, so a field-less one wrote `{}` for any value and a `tuple[int, int]` holding three items wrote two; a union handed the value back untouched, a live object that only `dump_file()` refused; a leaf was written as it was.
Refusing at `dump()` was rejected for the forensic reason above; a field-less struct's `{}` is what a descriptor-typed dataclass field dumped as, read as its descriptor class.
